"""Recommendations: build the daily digest (zero LLM calls), list, save, dismiss.

Logs carry ids and counts only.
"""

import logging
import time
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from app.agent.scoring import ScoreResult
from app.ai.embeddings import Embedder
from app.ai.jd_extractor import EXTRACTOR_VERSION
from app.core.clock import local_day
from app.core.config import settings
from app.core.exceptions import Conflict, NotFound
from app.models.discovery import CatalogJob, Recommendation
from app.models.job import NEW, Job
from app.repositories.manager import RepositoryManager
from app.schemas.job import JobDescription
from app.schemas.profile import ProfileData
from app.schemas.recommendation import RecommendationOut
from app.services.prefs import preferences_of
from app.tasks.jobs import Scorer, apply_score
from app.tasks.queue import TaskQueue
from app.vector.index import BruteForceIndex, SearchFilters, VectorIndex

log = logging.getLogger(__name__)

# Profile vectors cached per approved version (user, profile id, embedder).
_PROFILE_VECTORS: dict[tuple[str, str, str], list[float]] = {}


@dataclass
class ScoringContext:
    """The part of TaskContext that Scorer reads (so the API need not build a full one)."""

    scoring: object
    embedder: Embedder


def profile_summary(data: ProfileData, target_roles: list[str]) -> str:
    parts = [data.summary or "", *target_roles, ", ".join(data.skills)]
    for e in data.experience:
        parts.append(f"{e.title or ''} {e.company}")
        parts.extend(b.text for b in e.bullets[:3])
    for p in data.projects:
        parts.append(p.name)
    return "\n".join(x for x in parts if x)


def profile_vector(
    repos: RepositoryManager, embedder: Embedder, user_id: uuid.UUID
) -> list[float] | None:
    profile = repos.profiles.get_latest_approved(user_id)
    if profile is None:
        return None
    key = (str(user_id), f"{profile.id}", embedder.name)
    if key not in _PROFILE_VECTORS:
        prefs = preferences_of(repos.users.get(user_id))
        text = profile_summary(
            ProfileData.model_validate(profile.data), prefs.target_roles
        )
        (_PROFILE_VECTORS[key],) = embedder.embed_queries([text])
    return _PROFILE_VECTORS[key]


def load_catalog_index(
    repos: RepositoryManager, since: datetime, embedder_name: str
) -> BruteForceIndex:
    index = BruteForceIndex()
    for r in repos.catalog.searchable(since):
        if r.embedding_model != embedder_name:
            continue  # vectors from another model are not comparable
        index.upsert(
            r.id,
            r.embedding or [],
            {
                "closed_at": r.closed_at,
                "first_seen": r.first_seen,
                "remote": r.remote,
                "country_restrictions": r.country_restrictions or [],
                "city": r.city,
            },
        )
    return index


def reasons_from(result: ScoreResult, job: CatalogJob) -> list[str]:
    """Plain facts from the score breakdown. Never produced by a model."""
    out: list[str] = []
    musts = result.musts
    if musts:
        have = [m.skill for m in musts if m.status == "have"]
        out.append(
            f"Matches {len(have)} of {len(musts)} must-have skills"
            + (f": {', '.join(have[:4])}" if have else "")
        )
        ask = [m.skill for m in musts if m.status == "ask"]
        if ask:
            out.append(f"You may also cover: {', '.join(ask[:3])}")
    b = result.breakdown
    if b.get("experience_fit", {}).get("value", 0) >= 1.0:
        out.append("Your experience fits the requested range")
    if b.get("location_fit", {}).get("value", 0) >= 1.0:
        out.append("Remote" if job.remote else f"Located in {job.city or job.location}")
    if b.get("ctc_fit", {}).get("value", 0) >= 1.0 and (
        b.get("ctc_fit", {}).get("value") is not None
    ):
        out.append("Pay is within your expectation")
    return out


def build_recommendations(
    ctx,
    user_id: uuid.UUID | str,
    *,
    index: VectorIndex | None = None,
    now: datetime | None = None,
) -> int:
    """profile vector -> vector search -> exclusions -> v1 score -> top N -> digest.

    No LLM is called. Returns the number of recommendations in today's digest.
    """
    user_id = uuid.UUID(str(user_id))
    now = now or datetime.now(UTC)
    with ctx.session_factory() as session:
        repos = RepositoryManager(session)
        user = repos.users.get(user_id)
        if user is None or user.status != "active":
            return 0
        vector = profile_vector(repos, ctx.embedder, user_id)
        scorer = Scorer(repos, ctx, user_id)
        if vector is None or scorer.facts is None:
            log.info("build_recommendations: no approved profile user=%s", user_id)
            return 0
        prefs = preferences_of(user)
        since = now - timedelta(days=settings.reco_max_age_days)
        idx = index or load_catalog_index(repos, since, ctx.embedder.name)
        filters = SearchFilters(
            open_only=True,
            first_seen_after=since,
            cities=tuple(c for c in prefs.cities if c != "Remote"),
            country=settings.reco_user_country,
        )
        hits = idx.search(vector, settings.reco_candidates_k, filters)
        excluded = repos.recommendations.excluded_catalog_ids(user_id)
        rows = repos.catalog.by_ids([h.id for h in hits if h.id not in excluded])
        scored: list[tuple[int, str, ScoreResult]] = []
        for h in hits:
            job = rows.get(h.id)
            if (
                job is None
                or not job.jd
                or job.closed_at is not None
                or job.duplicate_of
            ):
                continue
            result = scorer.score(JobDescription.model_validate(job.jd))
            if result.score is not None:
                scored.append((result.score, job.id, result))
        scored.sort(key=lambda t: (-t[0], t[1]))
        top = scored[: settings.reco_digest_size]
        digest = local_day(now)
        repos.recommendations.replace_digest(
            user_id,
            digest,
            [
                Recommendation(
                    user_id=user_id,
                    catalog_job_id=cid,
                    score=score,
                    reasons=reasons_from(result, rows[cid]),
                    digest_date=digest,
                )
                for score, cid, result in top
            ],
        )
        log.info(
            "build_recommendations user=%s candidates=%d digest=%d",
            user_id,
            len(hits),
            len(top),
        )
        return len(top)


def _out(
    rec: Recommendation, job: CatalogJob, company: str | None
) -> RecommendationOut:
    return RecommendationOut(
        id=rec.id,
        catalog_job_id=job.id,
        score=rec.score,
        reasons=rec.reasons or [],
        digest_date=rec.digest_date,
        action=rec.action,
        job_id=rec.job_id,
        title=job.title,
        company=company,
        location=job.location,
        remote=job.remote,
        apply_url=job.apply_url,
        source_attribution=job.source_attribution,
    )


_last_sync = float("-inf")
SYNC_COOLDOWN_S = 30 * 60


class RecommendationService:
    def __init__(
        self, repos: RepositoryManager, queue: TaskQueue, ctx: ScoringContext
    ) -> None:
        self.repos, self.queue, self.ctx = repos, queue, ctx

    def _own(self, user_id: uuid.UUID, rec_id: str) -> Recommendation:
        rec = self.repos.recommendations.get_for_user(user_id, rec_id)
        if rec is None:
            log.info("recommendation not found user=%s rec=%s", user_id, rec_id)
            raise NotFound("Recommendation not found")
        return rec

    def _present(self, recs: list[Recommendation]) -> list[RecommendationOut]:
        jobs = self.repos.catalog.by_ids([r.catalog_job_id for r in recs])
        out = []
        for r in recs:
            job = jobs.get(r.catalog_job_id)
            if job is None:
                continue
            company = self.repos.catalog.company(job.company_id)
            out.append(_out(r, job, company.name if company else None))
        return out

    def today(self, user_id: uuid.UUID) -> list[RecommendationOut]:
        return self._present(self.repos.recommendations.digest(user_id, local_day()))

    def refresh(self, user_id: uuid.UUID) -> str:
        """Make sure the user has a digest without waiting for the daily run.

        Returns ready | building | syncing. Cheap and idempotent: enqueues at most one
        task per call, and discovery itself at most once per cooldown (in this process).
        """
        global _last_sync
        if self.repos.recommendations.digest(user_id, local_day()):
            return "ready"
        if self.repos.catalog.count_open() == 0:
            now = time.monotonic()
            if now - _last_sync > SYNC_COOLDOWN_S:
                _last_sync = now
                self.queue.enqueue(
                    "sync_catalog"
                )  # finishes by queueing every user's digest
            log.info(
                "recommendations refresh user=%s: catalogue empty, syncing", user_id
            )
            return "syncing"
        self.queue.enqueue("build_recommendations", user_id=str(user_id))
        log.info("recommendations refresh user=%s: building", user_id)
        return "building"

    def dismiss(
        self, user_id: uuid.UUID, rec_id: str, reason: str | None
    ) -> RecommendationOut:
        rec = self._own(user_id, rec_id)
        if rec.action == "saved":
            raise Conflict("Already saved", code="invalid_state")
        if reason or rec.action != "dismissed":  # a repeat keeps the first reason
            rec.dismiss_reason = reason or None
        rec.action = "dismissed"
        self.repos.recommendations.update(rec)
        log.info("recommendation dismissed user=%s rec=%s", user_id, rec.id)
        return self._present([rec])[0]

    def save(self, user_id: uuid.UUID, rec_id: str) -> RecommendationOut:
        """Create a v1 job from the catalogue JD (no extractor call), then score it."""
        rec = self._own(user_id, rec_id)
        cat = self.repos.catalog.by_id(rec.catalog_job_id)
        if cat is None or not cat.jd:
            raise NotFound("This posting is no longer available")
        job = self.repos.recommendations.job_for_catalog(user_id, cat.id)
        if job is None:
            jd = JobDescription.model_validate(cat.jd)
            company = self.repos.catalog.company(cat.company_id)
            jd = jd.model_copy(
                update={
                    "company": jd.company or (company.name if company else None),
                    "title": jd.title or cat.title,
                }
            )
            job = self.repos.jobs.add(
                Job(
                    user_id=user_id,
                    source="url",
                    url=cat.apply_url[:2048],
                    raw_text=cat.raw_text,
                    content_hash=cat.content_hash,
                    catalog_job_id=cat.id,
                    source_channel="recommended",
                    status="processing",
                )
            )
            self.repos.jobs.save_extraction(
                user_id, job.id, jd.model_dump(mode="json"), EXTRACTOR_VERSION
            )
            apply_score(job, jd, Scorer(self.repos, self.ctx, user_id).score(jd))  # type: ignore[arg-type]
            job.status, job.status_reason = NEW, None
            self.repos.jobs.update(job)
            self.repos.jobs.add_event(
                user_id,
                "job_ready",
                {"job_id": job.id, "score": job.score, "status": job.status},
            )
            log.info(
                "recommendation saved user=%s rec=%s job=%s", user_id, rec.id, job.id
            )
        rec.action, rec.job_id = "saved", job.id
        self.repos.recommendations.update(rec)
        return self._present([rec])[0]
