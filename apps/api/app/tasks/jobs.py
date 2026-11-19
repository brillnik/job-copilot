"""Background tasks for jobs. Each takes user_id explicitly and re-checks ownership.

Logs carry ids and hashes only, never posting text.
"""

import hashlib
import logging
import re
import time
import uuid
from collections.abc import Callable
from dataclasses import dataclass
from datetime import date

from sqlalchemy.orm import Session

from app.agent.scoring import (
    Prefs,
    ProfileFacts,
    ScoreResult,
    ScoringConfig,
    score_job,
)
from app.ai.embeddings import Embedder
from app.ai.errors import TransientError
from app.ai.fetcher import FetchError, JobTextFetcher, is_login_walled
from app.ai.jd_extractor import EXTRACTOR_VERSION, ImageTranscriber, JdExtractor
from app.core.config import settings
from app.core.exceptions import AppError
from app.models.job import ARCHIVED, FAILED, NEEDS_PASTE, NEW, Job
from app.repositories.manager import RepositoryManager
from app.schemas.job import JobDescription
from app.schemas.profile import ProfileData
from app.services.profile_index import approved_with_index
from app.storage.base import Storage

log = logging.getLogger(__name__)


@dataclass
class TaskContext:
    session_factory: Callable[[], Session]
    storage: Storage
    extractor: JdExtractor
    transcriber: ImageTranscriber
    fetcher: JobTextFetcher
    embedder: Embedder
    scoring: ScoringConfig
    sleep: Callable[[float], None] = time.sleep


def scoring_config() -> ScoringConfig:
    return ScoringConfig(
        w_must=settings.w_must,
        w_experience=settings.w_experience,
        w_location=settings.w_location,
        w_ctc=settings.w_ctc,
        w_nice=settings.w_nice,
        evidence_min_score=settings.evidence_min_score,
        ask_credit=settings.ask_credit,
        neutral_fit=settings.neutral_fit,
        overqualified_fit=settings.overqualified_fit,
        adjacency=settings.skill_adjacency,
        synonyms=settings.skill_synonyms,
    )


def normalise_text(text: str) -> str:
    return re.sub(r"[ \t]+", " ", re.sub(r"\r\n?", "\n", text)).strip()


def content_hash(text: str) -> str:
    canon = re.sub(r"\s+", " ", text.lower()).strip()
    return hashlib.sha256(canon.encode()).hexdigest()


# --- profile facts ----------------------------------------------------------
_YM = re.compile(r"^(\d{4})(?:-(\d{1,2}))?$")


def _month_index(value: str | None, today: date) -> int | None:
    if not value:
        return None
    if value.strip().lower() == "present":
        return today.year * 12 + today.month
    m = _YM.match(value.strip())
    if not m:
        return None
    return int(m.group(1)) * 12 + int(m.group(2) or 1)


def years_of_experience(data: ProfileData, today: date | None = None) -> float | None:
    """Total years across roles, merging overlaps; None if no role has a usable start."""
    today = today or date.today()
    spans = []
    for e in data.experience:
        start = _month_index(e.start, today)
        end = _month_index(e.end, today) if e.end else start
        if start is not None and end is not None and end >= start:
            spans.append((start, end))
    if not spans:
        return None
    spans.sort()
    total, (cur_s, cur_e) = 0, spans[0]
    for s, e in spans[1:]:
        if s <= cur_e:
            cur_e = max(cur_e, e)
        else:
            total += cur_e - cur_s
            cur_s, cur_e = s, e
    total += cur_e - cur_s
    return round(total / 12, 1)


class Scorer:
    """Scores jobs against one user's APPROVED profile; all lookups filter by user_id."""

    def __init__(self, repos: RepositoryManager, ctx: TaskContext, user_id: uuid.UUID):
        self.cfg = ctx.scoring
        self.answers = repos.jobs.answers(user_id)
        found = approved_with_index(repos, ctx.embedder, user_id)
        self.facts: ProfileFacts | None = None
        self._bullets = []
        self._embedder = ctx.embedder
        if found:
            profile, self._bullets = found
            data = ProfileData.model_validate(profile.data)
            self.facts = ProfileFacts(
                skills=data.skills,
                bullets=[(b.source_id, b.text) for b in self._bullets],
                years_experience=years_of_experience(data),
                location=data.contact.location,
            )
        self._cache: dict[str, tuple[str, float] | None] = {}

    def _evidence(self, skill: str) -> tuple[str, float] | None:
        if skill in self._cache:
            return self._cache[skill]
        best = None
        if self._bullets:
            (qv,) = self._embedder.embed_queries([skill])
            scored = (
                (sum(a * c for a, c in zip(qv, b.embedding, strict=False)), b)
                for b in self._bullets
            )
            score, bullet = max(scored, key=lambda t: t[0])
            best = (bullet.source_id, score)
        self._cache[skill] = best
        return best

    def score(self, jd: JobDescription) -> ScoreResult:
        return score_job(
            jd, self.facts, self.answers, self._evidence, self.cfg, Prefs()
        )


def apply_score(job: Job, jd: JobDescription, result: ScoreResult) -> None:
    job.score = result.score
    job.score_breakdown = result.breakdown
    job.musts = [m.model_dump() for m in result.musts]
    job.company = jd.company
    job.title = jd.title
    job.red_flags = jd.red_flags


# --- extract_jd -------------------------------------------------------------
class _NeedsPaste(Exception):
    pass


def _acquire_text(job: Job, repos: RepositoryManager, ctx: TaskContext) -> str:
    if job.raw_text:  # pasted, or kept from an earlier attempt
        return job.raw_text
    if job.source == "image":
        img = repos.jobs.get_image(job.user_id, job.image_id or "")
        if img is None:
            raise _NeedsPaste("The screenshot is no longer available; paste the text")
        text = normalise_text(
            ctx.transcriber.transcribe(
                ctx.storage.read(img.storage_key), img.media_type
            )
        )
    elif job.source == "url":
        url = job.url or ""
        if is_login_walled(url, settings.login_walled_domains):
            raise _NeedsPaste("This site needs a login; paste the job text instead")
        try:
            text = normalise_text(ctx.fetcher.fetch(url))
        except FetchError as e:
            raise _NeedsPaste(
                f"Could not read the page ({e}); paste the job text"
            ) from e
        if len(text) < settings.min_page_chars:
            raise _NeedsPaste("The page had too little text; paste the job text")
    else:
        raise _NeedsPaste("No job text available")
    if not text:
        raise _NeedsPaste("No text could be read; paste the job text")
    return text


def _set(job: Job, repos: RepositoryManager, status: str, reason: str | None) -> None:
    job.status, job.status_reason = status, reason
    repos.jobs.update(job)


def extract_jd(
    ctx: TaskContext,
    user_id: uuid.UUID | str,
    job_id: str,
) -> None:
    user_id = uuid.UUID(str(user_id))
    with ctx.session_factory() as session:
        repos = RepositoryManager(session)
        job = repos.jobs.get_for_user(user_id, job_id)
        if job is None or job.status == ARCHIVED:
            log.info(
                "extract_jd skipped user=%s job=%s reason=%s",
                user_id,
                job_id,
                "missing" if job is None else "archived",
            )
            return  # deleted or archived while queued: nothing to do

        retries = settings.job_task_retries
        for attempt in range(retries + 1):
            try:
                _extract_once(ctx, repos, job)
                return
            except _NeedsPaste as e:
                # The reason is user-facing copy, not posting text, so it is safe to log.
                log.info("extract_jd needs paste job=%s reason=%s", job.id, e)
                _set(job, repos, NEEDS_PASTE, str(e))
                repos.jobs.add_event(
                    user_id, "job_needs_paste", {"job_id": job.id, "reason": str(e)}
                )
                return
            except TransientError as e:
                log.warning(
                    "extract_jd transient job=%s attempt=%d: %s", job.id, attempt, e
                )
                if attempt < retries:
                    ctx.sleep(settings.job_task_backoff_s * 2**attempt)
                    continue
                reason = "Temporary problem reading the posting; try again"
                log.error(
                    "extract_jd gave up job=%s after %d attempts", job.id, attempt + 1
                )
            except AppError as e:
                log.warning("extract_jd failed job=%s code=%s", job.id, e.code)
                reason = e.detail
            except Exception as e:  # noqa: BLE001 - a task must never die silently
                # Type only: an exception message can echo the posting text.
                log.error(
                    "extract_jd crashed job=%s error=%s", job.id, type(e).__name__
                )
                reason = "Unexpected error while reading the posting"
            _set(job, repos, FAILED, reason)
            repos.jobs.add_event(
                user_id, "job_failed", {"job_id": job.id, "reason": reason}
            )
            return


def _extract_once(ctx: TaskContext, repos: RepositoryManager, job: Job) -> None:
    text = _acquire_text(job, repos, ctx)
    # Keep the input so a retry or PATCH {text} never needs the original source.
    job.raw_text = text
    job.content_hash = job.content_hash or content_hash(text)

    jd = ctx.extractor.extract(text, job.url)
    repos.jobs.save_extraction(
        job.user_id, job.id, jd.model_dump(mode="json"), EXTRACTOR_VERSION
    )
    apply_score(job, jd, Scorer(repos, ctx, job.user_id).score(jd))
    job.status, job.status_reason = NEW, None
    repos.jobs.update(job)
    repos.jobs.add_event(
        job.user_id,
        "job_ready",
        {"job_id": job.id, "score": job.score, "status": job.status},
    )
    log.info("job ready id=%s hash=%s", job.id, job.content_hash)


# --- rescore_jobs -----------------------------------------------------------
def rescore_jobs(ctx: TaskContext, user_id: uuid.UUID | str) -> int:
    """Recompute score and musts for open jobs. No LLM calls."""
    user_id = uuid.UUID(str(user_id))
    with ctx.session_factory() as session:
        repos = RepositoryManager(session)
        scorer = Scorer(repos, ctx, user_id)
        if scorer.facts is None:
            log.warning("rescore_jobs: no approved profile user=%s", user_id)
        count = 0
        for job in repos.jobs.rescorable(user_id):
            row = repos.jobs.extraction_for(user_id, job.id)
            if row is None:
                log.debug("rescore skipped job=%s reason=no_extraction", job.id)
                continue
            jd = JobDescription.model_validate(row.jd)
            result = scorer.score(jd)
            job.score = result.score
            job.score_breakdown = result.breakdown
            job.musts = [m.model_dump() for m in result.musts]
            count += 1
        session.commit()
        repos.jobs.add_event(user_id, "jobs_rescored", {"count": count})
        log.info("rescore_jobs done user=%s rescored=%d", user_id, count)
        return count


# --- tailor (stub) ----------------------------------------------------------
def tailor(ctx: TaskContext, user_id: uuid.UUID | str, run_id: str) -> None:
    user_id = uuid.UUID(str(user_id))
    with ctx.session_factory() as session:
        run = RepositoryManager(session).jobs.get_run(user_id, run_id)
        if run is None:
            return
        # TODO: the tailoring agent is not built yet. The run stays "queued", pinned
        # to its profile_version, until the agent exists.
        log.info("tailor stub run=%s profile_version=%s", run.id, run.profile_version)
