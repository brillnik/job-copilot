import logging
import math
import time
import uuid
from datetime import UTC, datetime
from typing import BinaryIO

from app.ai.embeddings import Embedder
from app.ai.extractor import ProfileExtractor
from app.core.exceptions import NotFound
from app.models.profile import DRAFT, Profile, ProfileBullet
from app.repositories.manager import RepositoryManager
from app.schemas.profile import (
    BulletSearch,
    BulletSearchOut,
    ProfileData,
    RankedBullet,
)
from app.services.profile_index import current_index
from app.services.resume import ResumeService
from app.tasks.queue import TaskQueue

log = logging.getLogger(__name__)


def _dump(data: ProfileData) -> dict:
    return data.model_dump(mode="json")


def _entries(data: ProfileData):
    """Yield (section, entry id, label, bullets) for every bullet-bearing entry."""
    for e in data.experience:
        label = " — ".join(p for p in (e.title, e.company) if p)
        yield "experience", e.id, label, e.bullets
    for p in data.projects:
        yield "project", p.id, p.name, p.bullets


class ProfileService:
    def __init__(
        self,
        repos: RepositoryManager,
        resumes: ResumeService,
        extractor: ProfileExtractor,
        embedder: Embedder,
        queue: TaskQueue | None = None,
    ) -> None:
        self.repos = repos
        self.resumes = resumes
        self.extractor = extractor
        self.embedder = embedder
        self.queue = queue

    def upload(self, user_id: uuid.UUID, filename: str, stream: BinaryIO) -> Profile:
        """Store the resume, extract it with Claude, and (re)create the draft."""
        resume, data = self.resumes.ingest(user_id, filename, stream)
        started = time.perf_counter()
        try:
            extracted = self.extractor.extract(filename, data)
        except Exception as e:
            # Type only: the message can echo resume content.
            log.error(
                "profile extraction failed user=%s resume=%s error=%s after %.1fs",
                user_id,
                resume.id,
                type(e).__name__,
                time.perf_counter() - started,
            )
            raise
        log.info(
            "profile extracted user=%s resume=%s in %.1fs",
            user_id,
            resume.id,
            time.perf_counter() - started,
        )
        return self._save_draft(user_id, extracted, resume.id)

    def get_approved(self, user_id: uuid.UUID) -> Profile:
        profile = self.repos.profiles.get_latest_approved(user_id)
        if profile is None:
            log.debug("no approved profile user=%s", user_id)
            raise NotFound("No approved profile yet")
        return profile

    def get_draft(self, user_id: uuid.UUID) -> Profile:
        draft = self.repos.profiles.get_draft(user_id)
        if draft is None:
            log.debug("no draft profile user=%s", user_id)
            raise NotFound("No draft profile")
        return draft

    def save_draft(self, user_id: uuid.UUID, data: ProfileData) -> Profile:
        return self._save_draft(user_id, data, None)

    def _save_draft(
        self, user_id: uuid.UUID, data: ProfileData, resume_id: str | None
    ) -> Profile:
        draft = self.repos.profiles.get_draft(user_id)
        if draft is None:
            created = self.repos.profiles.add(
                Profile(
                    user_id=user_id,
                    status=DRAFT,
                    data=_dump(data),
                    resume_id=resume_id,
                )
            )
            log.info("draft created user=%s profile=%s", user_id, created.id)
            return created
        draft.data = _dump(data)
        if resume_id:
            draft.resume_id = resume_id
        log.info("draft updated user=%s profile=%s", user_id, draft.id)
        return self.repos.profiles.update(draft)

    def add_confirmed_skill(self, user_id: uuid.UUID, skill: str) -> Profile | None:
        """Add a skill the user just confirmed to their draft (made from the approved
        profile if there is no draft yet). It is only claimable on a resume once they
        approve the draft, like any other profile edit."""
        draft = self.repos.profiles.get_draft(user_id)
        base = draft or self.repos.profiles.get_latest_approved(user_id)
        if base is None:
            return None
        data = ProfileData.model_validate(base.data)
        if skill.lower() in {s.lower() for s in data.skills}:
            return draft
        data.skills = [*data.skills, skill]
        log.info("confirmed skill added to draft user=%s", user_id)
        return self._save_draft(user_id, data, None)

    def approve(self, user_id: uuid.UUID) -> Profile:
        """Freeze the draft as a new version and index its bullets for retrieval."""
        draft = self.get_draft(user_id)
        data = ProfileData.model_validate(draft.data)

        rows = []
        for section, entry_id, label, bullets in _entries(data):
            for b in bullets:
                rows.append((section, entry_id, label, b))
        started = time.perf_counter()
        try:
            vectors = self.embedder.embed_documents(
                [f"{label}: {b.text}" for _, _, label, b in rows]
            )
        except Exception as e:
            log.error(
                "approve embedding failed user=%s profile=%s bullets=%d error=%s",
                user_id,
                draft.id,
                len(rows),
                type(e).__name__,
            )
            raise
        log.debug(
            "embedded %d bullets with %s in %.2fs",
            len(rows),
            self.embedder.name,
            time.perf_counter() - started,
        )
        version = self.repos.profiles.next_version(user_id)
        index = [
            ProfileBullet(
                profile_id=draft.id,
                user_id=user_id,
                source_id=b.id,
                section=section,
                entry_id=entry_id,
                entry_label=label,
                text=b.text,
                embedding=vec,
                embedding_model=self.embedder.name,
            )
            for (section, entry_id, label, b), vec in zip(rows, vectors)
        ]
        approved = self.repos.profiles.approve(draft, version, datetime.now(UTC), index)
        log.info(
            "profile approved user=%s profile=%s version=%d bullets=%d embedder=%s",
            user_id,
            approved.id,
            version,
            len(index),
            self.embedder.name,
        )
        if self.queue is not None:  # indexing is done, so open jobs can be re-scored
            self.queue.enqueue("rescore_jobs", user_id=str(user_id))
        return approved

    def search_bullets(self, user_id: uuid.UUID, req: BulletSearch) -> BulletSearchOut:
        """Per-query vector search over the approved index, merged and diversity-capped."""
        profile = self.get_approved(user_id)
        bullets = current_index(self.repos, self.embedder, profile.id)
        floor = self.embedder.min_score if req.min_score is None else req.min_score
        queries = [q.strip() for q in req.queries if q.strip()]
        qvecs = self.embedder.embed_queries(queries)

        # source_id -> (best score, matched queries). Vectors are unit length.
        best: dict[str, tuple[float, list[str]]] = {}
        by_id = {b.source_id: b for b in bullets}
        for query, qv in zip(queries, qvecs):
            scored = sorted(
                ((sum(a * c for a, c in zip(qv, b.embedding)), b) for b in bullets),
                key=lambda t: t[0],
                reverse=True,
            )
            for score, b in scored[: req.per_query]:
                if score < floor or math.isnan(score):
                    continue
                prev_score, matched = best.get(b.source_id, (0.0, []))
                best[b.source_id] = (max(prev_score, score), [*matched, query])

        ranked: list[RankedBullet] = []
        per_entry: dict[str, int] = {}
        for sid, (score, matched) in sorted(
            best.items(),
            # Covering more must-haves beats a slightly higher single-query score.
            key=lambda kv: (len(kv[1][1]), kv[1][0]),
            reverse=True,
        ):
            b = by_id[sid]
            if per_entry.get(b.entry_id, 0) >= req.max_per_entry:
                continue
            per_entry[b.entry_id] = per_entry.get(b.entry_id, 0) + 1
            ranked.append(
                RankedBullet(
                    source_id=sid,
                    text=b.text,
                    section=b.section,
                    entry_id=b.entry_id,
                    entry_label=b.entry_label,
                    score=round(score, 4),
                    matched_queries=matched,
                )
            )
            if len(ranked) >= req.limit:
                break
        # Queries are job requirements, not personal data, but keep them out of INFO.
        log.debug(
            "bullet search user=%s profile=%s queries=%d bullets=%d floor=%.2f -> %d",
            user_id,
            profile.id,
            len(queries),
            len(bullets),
            floor,
            len(ranked),
        )
        return BulletSearchOut(profile_version=profile.version or 0, bullets=ranked)
