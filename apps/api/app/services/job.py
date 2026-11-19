import base64
import binascii
import logging
import uuid
from datetime import UTC, datetime, timedelta
from typing import BinaryIO
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse
from zoneinfo import ZoneInfo

from app.agent.scoring import musts_summary
from app.core.config import settings
from app.core.exceptions import (
    AppError,
    Conflict,
    EmptyFile,
    FileTooLarge,
    NotFound,
    TooManyRequests,
    UnsupportedFileType,
)
from app.models.job import (
    ARCHIVED,
    FAILED,
    NEEDS_PASTE,
    NEW,
    PROCESSING,
    ImageUpload,
    Job,
)
from app.repositories.job import QuotaExceeded, RunInProgress
from app.repositories.manager import RepositoryManager
from app.schemas.job import (
    JobAdd,
    JobAddOut,
    JobDescription,
    JobDetail,
    JobList,
    JobOut,
    JobPatch,
    JobSummary,
    Must,
    RunRef,
    TailorIn,
)
from app.storage.base import Storage
from app.tasks.jobs import content_hash, normalise_text
from app.tasks.queue import TaskQueue

# Logs carry ids, statuses and counts only: never posting URLs, text or screenshots.
log = logging.getLogger(__name__)

TRACKING_PARAMS = {
    "gclid", "fbclid", "msclkid", "igshid", "ref", "referrer", "source", "src",
    "trk", "trackingid", "mc_cid", "mc_eid", "lipi", "refid", "cmpid",
}  # fmt: skip

IMAGE_TYPES = {
    b"\x89PNG\r\n\x1a\n": ("image/png", ".png"),
    b"\xff\xd8\xff": ("image/jpeg", ".jpg"),
}


class Invalid(AppError):
    status_code = 422
    code = "validation_error"
    detail = "Invalid input"


def normalise_url(raw: str) -> str:
    """Canonical form for duplicate detection: no tracking params, fragment or trailing slash."""
    p = urlparse(raw.strip())
    if p.scheme.lower() not in ("http", "https") or not p.hostname:
        raise Invalid("url must be an http(s) link")
    host = p.hostname.lower()
    port = p.port
    if port and port not in (80 if p.scheme == "http" else 443,):
        host = f"{host}:{port}"
    query = sorted(
        (k, v)
        for k, v in parse_qsl(p.query, keep_blank_values=True)
        if not k.lower().startswith("utm_") and k.lower() not in TRACKING_PARAMS
    )
    path = p.path.rstrip("/")
    return urlunparse((p.scheme.lower(), host, path, "", urlencode(query), ""))


def local_day(now: datetime | None = None) -> str:
    return (
        (now or datetime.now(UTC))
        .astimezone(ZoneInfo(settings.day_timezone))
        .date()
        .isoformat()
    )


def _summary(job: Job, jd: dict | None) -> JobSummary:
    jd = jd or {}
    return JobSummary(
        id=job.id,
        company=job.company,
        title=job.title,
        location=jd.get("location"),
        ctc_lpa_min=jd.get("ctc_lpa_min"),
        ctc_lpa_max=jd.get("ctc_lpa_max"),
        score=job.score,
        musts_summary=musts_summary(job.musts or []),
        status=job.status,
        red_flags=job.red_flags or [],
        created_at=job.created_at,
    )


class JobService:
    def __init__(
        self,
        repos: RepositoryManager,
        queue: TaskQueue,
        storage: Storage,
    ) -> None:
        self.repos = repos
        self.queue = queue
        self.storage = storage

    def _own(self, user_id: uuid.UUID, job_id: str) -> Job:
        job = self.repos.jobs.get_for_user(user_id, job_id)
        if job is None:
            # Also what a request for someone else's job looks like.
            log.info("job not found user=%s job=%s", user_id, job_id)
            raise NotFound("Job not found")
        return job

    # --- images -------------------------------------------------------------
    def upload_image(self, user_id: uuid.UUID, stream: BinaryIO) -> ImageUpload:
        data = stream.read(settings.max_image_bytes + 1)
        if len(data) > settings.max_image_bytes:
            log.warning(
                "image rejected user=%s reason=too_large limit=%d",
                user_id,
                settings.max_image_bytes,
            )
            raise FileTooLarge(f"Image exceeds {settings.max_image_bytes} bytes")
        if not data:
            log.warning("image rejected user=%s reason=empty", user_id)
            raise EmptyFile()
        kind = next(
            (v for magic, v in IMAGE_TYPES.items() if data.startswith(magic)), None
        )
        if kind is None:
            log.warning("image rejected user=%s reason=unsupported_type", user_id)
            raise UnsupportedFileType("Only PNG and JPEG screenshots are supported")
        media_type, ext = kind
        image_id = uuid.uuid4().hex
        key = f"{user_id.hex}/images/{image_id}{ext}"
        self.storage.save(key, data)
        try:
            image = self.repos.jobs.add(
                ImageUpload(
                    id=image_id,
                    user_id=user_id,
                    storage_key=key,
                    media_type=media_type,
                    size=len(data),
                )
            )
        except Exception as e:
            log.error(
                "image db insert failed id=%s error=%s; removing stored file",
                image_id,
                type(e).__name__,
            )
            self.storage.delete(key)
            raise
        log.info(
            "image uploaded user=%s id=%s type=%s size=%d",
            user_id,
            image_id,
            media_type,
            len(data),
        )
        return image

    # --- add ----------------------------------------------------------------
    def add(self, user_id: uuid.UUID, body: JobAdd) -> tuple[JobAddOut, bool]:
        """Returns (result, created). created=False means a duplicate was found."""
        url = text = digest = None
        if body.source == "url":
            url = normalise_url(body.url or "")
        elif body.source == "text":
            text = normalise_text(body.text or "")
            if not text:
                raise Invalid("text must not be empty")
            digest = content_hash(text)
        elif self.repos.jobs.get_image(user_id, body.image_id or "") is None:
            log.info("job add: image not found user=%s", user_id)
            raise NotFound("Image not found")

        if body.source != "image":
            dup = self.repos.jobs.find_duplicate(user_id, url, digest)
            if dup is not None:
                log.info(
                    "job add: duplicate user=%s source=%s existing=%s",
                    user_id,
                    body.source,
                    dup.id,
                )
                return JobAddOut(job_id=dup.id, duplicate=True), False

        used = self.repos.jobs.count_created_since(
            user_id, datetime.now(UTC) - timedelta(hours=1)
        )
        if used >= settings.jobs_per_hour:
            log.warning(
                "job add: rate limited user=%s used=%d limit=%d",
                user_id,
                used,
                settings.jobs_per_hour,
            )
            raise TooManyRequests(
                "Too many jobs added; try again later",
                code="rate_limited",
                details={"limit": settings.jobs_per_hour, "window": "1h"},
            )
        job = self.repos.jobs.add(
            Job(
                user_id=user_id,
                source=body.source,
                url=url,
                raw_text=text,
                image_id=body.image_id,
                content_hash=digest,
                status=PROCESSING,
            )
        )
        log.info(
            "job added user=%s job=%s source=%s hash=%s",
            user_id,
            job.id,
            body.source,
            digest,
        )
        self.queue.enqueue("extract_jd", user_id=str(user_id), job_id=job.id)
        return JobAddOut(job_id=job.id, status=PROCESSING), True

    # --- read ---------------------------------------------------------------
    def list(
        self,
        user_id: uuid.UUID,
        *,
        status: str | None,
        min_score: int | None,
        city: str | None,
        q: str | None,
        sort: str,
        cursor: str | None,
        limit: int,
    ) -> JobList:
        offset = 0
        if cursor:
            try:
                offset = max(0, int(base64.urlsafe_b64decode(cursor.encode()).decode()))
            except (ValueError, binascii.Error):
                log.info("job list: invalid cursor user=%s", user_id)
                raise Invalid("Invalid cursor") from None
        rows = self.repos.jobs.list_for_user(
            user_id,
            status=status,
            min_score=min_score,
            city=city,
            q=q,
            sort=sort,
            offset=offset,
            limit=limit + 1,
        )
        page = rows[:limit]
        jds = self.repos.jobs.extractions_for(user_id, [j.id for j in page])
        nxt = (
            base64.urlsafe_b64encode(str(offset + limit).encode()).decode()
            if len(rows) > limit
            else None
        )
        # Filter values (city, q) are user input; log only which filters were used.
        log.debug(
            "job list user=%s filters=%s sort=%s offset=%d -> %d rows, more=%s",
            user_id,
            [
                name
                for name, v in (
                    ("status", status),
                    ("min_score", min_score),
                    ("city", city),
                    ("q", q),
                )
                if v is not None
            ],
            sort,
            offset,
            len(page),
            nxt is not None,
        )
        return JobList(
            items=[_summary(j, jds[j.id].jd if j.id in jds else None) for j in page],
            next_cursor=nxt,
        )

    def detail(self, user_id: uuid.UUID, job_id: str) -> JobDetail:
        job = self._own(user_id, job_id)
        ext = self.repos.jobs.extraction_for(user_id, job.id)
        run = self.repos.jobs.latest_run(user_id, job.id)
        return JobDetail(
            job=JobOut.model_validate(job),
            jd=JobDescription.model_validate(ext.jd) if ext else None,
            score_breakdown=job.score_breakdown,
            musts=[Must.model_validate(m) for m in job.musts or []],
            latest_run=RunRef(id=run.id, status=run.status) if run else None,
        )

    # --- patch --------------------------------------------------------------
    def patch(self, user_id: uuid.UUID, job_id: str, body: JobPatch) -> JobDetail:
        job = self._own(user_id, job_id)
        fields = body.model_fields_set
        if "text" in fields:
            if job.status not in (NEEDS_PASTE, FAILED):
                log.info(
                    "job patch rejected user=%s job=%s reason=invalid_state status=%s",
                    user_id,
                    job.id,
                    job.status,
                )
                raise Conflict(
                    "Text can only be added to a job that needs it",
                    code="invalid_state",
                    details={"status": job.status},
                )
            job.raw_text = normalise_text(body.text or "")
            job.content_hash = content_hash(job.raw_text)
            job.status, job.status_reason = PROCESSING, None
            self.repos.jobs.update(job)
            log.info("job text pasted user=%s job=%s; re-extracting", user_id, job.id)
            self.queue.enqueue("extract_jd", user_id=str(user_id), job_id=job.id)
        elif "archived" in fields:
            self._set_archived(user_id, job, bool(body.archived))
        else:
            job.max_pages_override = body.max_pages_override
            self.repos.jobs.update(job)
            log.info(
                "job max_pages_override set user=%s job=%s value=%s",
                user_id,
                job.id,
                job.max_pages_override,
            )
        return self.detail(user_id, job.id)

    def _set_archived(self, user_id: uuid.UUID, job: Job, archived: bool) -> None:
        before = job.status
        if archived:
            job.status = ARCHIVED
        elif job.status == ARCHIVED:
            if self.repos.jobs.extraction_for(user_id, job.id):
                job.status = NEW
            else:  # archived before extraction finished: run it again
                job.status = PROCESSING
                self.queue.enqueue("extract_jd", user_id=str(user_id), job_id=job.id)
        self.repos.jobs.update(job)
        log.info(
            "job %s user=%s job=%s status %s -> %s",
            "archived" if archived else "unarchived",
            user_id,
            job.id,
            before,
            job.status,
        )

    # --- tailor -------------------------------------------------------------
    def tailor(self, user_id: uuid.UUID, job_id: str, body: TailorIn) -> str:
        job = self._own(user_id, job_id)

        def refuse(reason: str, **extra: object) -> None:
            log.info(
                "tailor refused user=%s job=%s reason=%s status=%s %s",
                user_id,
                job.id,
                reason,
                job.status,
                extra or "",
            )

        if job.status in (PROCESSING, NEEDS_PASTE, FAILED):
            refuse("jd_not_ready")
            raise Conflict(
                "The job description is not ready", code="jd_not_ready",
                details={"status": job.status},
            )  # fmt: skip
        if job.status == ARCHIVED:
            refuse("archived")
            raise Conflict("The job is archived", code="invalid_state")
        if job.red_flags and not body.confirm_red_flags:
            refuse("red_flags", count=len(job.red_flags))
            raise Conflict(
                "This posting has red flags; confirm to continue",
                code="red_flags",
                details={"red_flags": job.red_flags},
            )
        profile = self.repos.profiles.get_latest_approved(user_id)
        if profile is None:
            refuse("no_profile")
            raise Conflict("Approve your profile first", code="no_profile")
        if profile.indexing_state != "done":
            refuse("profile_indexing", state=profile.indexing_state)
            raise Conflict(
                "Your profile is still being indexed", code="profile_indexing"
            )
        active = self.repos.jobs.active_run(user_id, job.id)
        if active:
            refuse("run_in_progress", run=active.id)
            raise Conflict(
                "A run is already in progress", code="run_in_progress",
                details={"run_id": active.id},
            )  # fmt: skip

        day, cap = local_day(), settings.daily_run_cap
        try:
            run = self.repos.jobs.reserve_run(
                user_id, job, profile.version or 0, day, cap
            )
        except QuotaExceeded as e:
            log.warning(
                "tailor daily cap reached user=%s job=%s used=%s cap=%d day=%s",
                user_id,
                job.id,
                e.used,
                cap,
                day,
            )
            raise TooManyRequests(
                "Daily run limit reached", code="daily_cap",
                details={"used": e.used, "cap": cap},
            ) from None  # fmt: skip
        except RunInProgress as e:
            log.info(
                "tailor lost race user=%s job=%s existing_run=%s",
                user_id,
                job.id,
                e.run_id,
            )
            raise Conflict(
                "A run is already in progress", code="run_in_progress",
                details={"run_id": e.run_id},
            ) from None  # fmt: skip
        log.info(
            "tailor queued user=%s job=%s run=%s profile_version=%s day=%s",
            user_id,
            job.id,
            run.id,
            profile.version,
            day,
        )
        self.queue.enqueue("tailor", user_id=str(user_id), run_id=run.id)
        self.repos.jobs.add_event(
            user_id, "run_queued", {"job_id": job.id, "run_id": run.id}
        )
        return run.id
