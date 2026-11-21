"""Applications: create from an approved run, run state, caps, extension channel.

One application per (user, job). Slots in the per-user/site/ATS counters are taken
atomically before any attempt and given back unless the application is submitted.
Logs carry ids, statuses and reason codes only.
"""

import base64
import binascii
import logging
import uuid
from datetime import UTC, datetime

from sqlalchemy.exc import IntegrityError

from app.apply.adapters import ats_for_url
from app.apply.policy import BLOCK_REASONS, extension_site, is_linkedin
from app.core import signing
from app.core.clock import local_day
from app.core.config import settings
from app.core.exceptions import AppError, Conflict, NotFound, TooManyRequests
from app.models.application import ACTIVE, Application
from app.models.job import Job
from app.repositories.application import CapReached, Caps
from app.repositories.manager import RepositoryManager
from app.schemas.application import (
    ApplicationAnswerIn,
    ApplicationList,
    ApplicationOut,
    PendingField,
)
from app.schemas.job import JobDescription
from app.schemas.profile import ProfileData
from app.schemas.screening import ScreeningField
from app.services import paging
from app.services.autopilot_prefs import (
    autopilot_of,
    daily_cap,
    site_cap,
    site_opted_in,
)
from app.services.screening import ScreeningService, normalise
from app.services.tracker import TrackerService
from app.storage.base import Storage
from app.tasks.queue import TaskQueue

log = logging.getLogger(__name__)

ANSWER_TYPES = (
    "notice_period",
    "current_ctc",
    "expected_ctc",
    "relocation",
    "work_authorization",
)
LINK_KINDS = ("linkedin", "github", "portfolio")
CONTACT = ("name", "email", "phone", "location")


class Invalid(AppError):
    status_code = 422
    code = "validation_error"
    detail = "Invalid input"


class ApplyRefused(Conflict):
    code = "apply_refused"


def hour_key(now: datetime | None = None) -> str:
    return (now or datetime.now(UTC)).astimezone(UTC).strftime("%Y-%m-%dT%H")


class ApplicationService:
    def __init__(
        self,
        repos: RepositoryManager,
        queue: TaskQueue | None,
        storage: Storage,
        screening: ScreeningService | None = None,
    ) -> None:
        self.repos, self.queue, self.storage = repos, queue, storage
        self.screening = screening or ScreeningService(repos)
        self.tracker = TrackerService(repos)

    # --- lookup ------------------------------------------------------------
    def _own(self, user_id: uuid.UUID, app_id: str) -> Application:
        app = self.repos.applications.get_for_user(user_id, app_id)
        if app is None:
            log.info("application not found user=%s app=%s", user_id, app_id)
            raise NotFound("Application not found")
        return app

    def _user(self, user_id: uuid.UUID):
        return self.repos.users.get(user_id)

    def caps_for(self, user, app: Application) -> Caps:
        return Caps(
            user_day=daily_cap(user),
            site_day=site_cap(app.site),
            ats_hour=settings.autopilot_ats_hourly_cap
            if app.channel == "playwright"
            else None,
        )

    # --- create ------------------------------------------------------------
    def _apply_url(self, job: Job) -> tuple[str | None, str | None]:
        """(url, ats hint). Catalogue jobs always use their stored apply_url (for
        Himalayas: the applicationLink); other jobs use their own link."""
        if job.catalog_job_id:
            cat = self.repos.catalog.by_id(job.catalog_job_id)
            if cat is not None:
                hint = (
                    cat.source
                    if cat.source in ("greenhouse", "lever", "ashby")
                    else None
                )
                return cat.apply_url, hint
        return job.url, None

    def _refusal(self, user, channel: str, site: str, ats: str | None) -> str | None:
        if not settings.apply_enabled:
            return "kill_switch"
        if (
            channel == "playwright"
            and ats not in (None, "unknown")
            and ats not in settings.apply_enabled_ats
        ):
            return "ats_disabled"
        if channel == "extension" and not site_opted_in(user, site):
            return "site_not_opted_in"
        if site in self.repos.applications.paused_sites(user.id):
            return "site_paused"
        return None

    def create_for_run(
        self, user_id: uuid.UUID, run_id: str, *, mode: str = "manual"
    ) -> Application:
        run = self.repos.runs.get_for_user(user_id, run_id)
        if run is None:
            raise NotFound("Run not found")
        approval = self.repos.runs.approval_for(user_id, run_id)
        if (
            run.status != "approved"
            or approval is None
            or approval.decision != "approved"
            or not approval.pdf_key
        ):
            raise Conflict("Approve this run first", code="run_not_approved")
        job = self.repos.jobs.get_for_user(user_id, run.job_id)
        if job is None:
            raise NotFound("Job not found")
        existing = self.repos.applications.by_job(user_id, job.id)
        if existing is not None and (
            existing.status in ACTIVE
            or existing.status == "submitted"
            or mode == "autopilot"
        ):
            return existing  # one application per job; never a second attempt
        url, hint = self._apply_url(job)
        if not url:
            raise Invalid(
                "This job has no apply link",
            )
        if is_linkedin(url):
            raise Invalid(
                "LinkedIn is not supported",
            )
        site_name = extension_site(url)
        channel = "extension" if site_name else "playwright"
        ats = None if site_name else (hint or ats_for_url(url))
        site = site_name or ats or "unknown"
        user = self._user(user_id)
        refusal = self._refusal(user, channel, site, ats)
        if refusal and mode == "manual":
            raise ApplyRefused(
                "This application cannot be started",
                code=refusal,
                details={"site": site},
            )
        status = "skipped" if refusal else "queued"
        if existing is not None:  # manual retry of a skipped/failed/cancelled one
            self.repos.applications.cas_status(
                existing, ("skipped", "failed", "cancelled"), status,
                skip_reason=refusal, run_id=run_id, mode=mode, apply_url=url,
                channel=channel, ats=ats, site=site, error=None,
                pending_fields=[], provided_answers={},
            )  # fmt: skip
            self.repos.session.commit()
            app = existing
        else:
            app = Application(
                user_id=user_id, job_id=job.id, run_id=run_id, channel=channel,
                mode=mode, ats=ats, site=site, status=status, skip_reason=refusal,
                apply_url=url[:2048],
            )  # fmt: skip
            self.repos.session.add(app)
            try:
                self.repos.session.commit()
            except IntegrityError:  # a concurrent create won
                self.repos.session.rollback()
                won = self.repos.applications.by_job(user_id, job.id)
                if won is None:
                    raise
                return won
        log.info(
            "application created user=%s app=%s channel=%s status=%s reason=%s",
            user_id, app.id, channel, app.status, refusal,
        )  # fmt: skip
        self._dispatch(app)
        return app

    def _dispatch(self, app: Application) -> None:
        if (
            app.status == "queued"
            and app.channel == "playwright"
            and settings.apply_worker_mode == "inprocess"
            and self.queue is not None
        ):
            self.queue.enqueue(
                "apply_application", user_id=str(app.user_id), application_id=app.id
            )

    def record_skipped_run(
        self, user_id: uuid.UUID, run_id: str, reason: str
    ) -> Application | None:
        """Autopilot decided not to apply (e.g. flagged draft): a skipped application
        with the direct link, so the person can decide. Never queued, never submitted."""
        run = self.repos.runs.get_for_user(user_id, run_id)
        job = self.repos.jobs.get_for_user(user_id, run.job_id) if run else None
        if run is None or job is None:
            return None
        existing = self.repos.applications.by_job(user_id, job.id)
        if existing is not None:
            return existing
        url, hint = self._apply_url(job)
        if not url:
            return None
        site_name = extension_site(url)
        ats = None if site_name else (hint or ats_for_url(url))
        app = Application(
            user_id=user_id, job_id=job.id, run_id=run_id,
            channel="extension" if site_name else "playwright", mode="autopilot",
            ats=ats, site=site_name or ats or "unknown", status="skipped",
            skip_reason=reason, apply_url=url[:2048],
        )  # fmt: skip
        self.repos.session.add(app)
        try:
            self.repos.session.commit()
        except IntegrityError:
            self.repos.session.rollback()
            return self.repos.applications.by_job(user_id, job.id)
        return app

    # --- read --------------------------------------------------------------
    def _out(
        self, app: Application, job: Job | None, *, detail: bool
    ) -> ApplicationOut:
        shots = (
            [
                signing.sign(
                    k, min(settings.signed_url_ttl_s, 300), filename="proof.png"
                )
                for k in app.screenshot_keys or []
            ]
            if detail
            else []
        )
        return ApplicationOut(
            id=app.id, job_id=app.job_id, run_id=app.run_id,
            company=job.company if job else None, title=job.title if job else None,
            channel=app.channel, mode=app.mode, ats=app.ats, site=app.site,
            status=app.status, skip_reason=app.skip_reason, direct_link=app.apply_url,
            submitted_at=app.submitted_at,
            answers_used=app.answers_used or [] if detail else [],
            screenshots=shots,
            pending_fields=[PendingField(**p) for p in app.pending_fields or []],
            attempts=app.attempts, created_at=app.created_at, updated_at=app.updated_at,
        )  # fmt: skip

    def out(self, app: Application, *, detail: bool = True) -> ApplicationOut:
        return self._out(
            app, self.repos.jobs.get_for_user(app.user_id, app.job_id), detail=detail
        )

    def detail(self, user_id: uuid.UUID, app_id: str) -> ApplicationOut:
        return self.out(self._own(user_id, app_id))

    def list_apps(
        self, user_id: uuid.UUID, *, status: str | None, cursor: str | None, limit: int
    ) -> ApplicationList:
        offset = paging.decode(cursor)
        rows = self.repos.applications.list_for_user(
            user_id, status=status, offset=offset, limit=limit + 1
        )
        page = rows[:limit]
        jobs = self.repos.runs.jobs_for(user_id, [a.job_id for a in page])
        return ApplicationList(
            items=[self._out(a, jobs.get(a.job_id), detail=False) for a in page],
            next_cursor=paging.encode(offset + limit) if len(rows) > limit else None,
        )

    # --- user actions --------------------------------------------------------
    def answer(
        self, user_id: uuid.UUID, app_id: str, body: ApplicationAnswerIn
    ) -> ApplicationOut:
        app = self._own(user_id, app_id)
        if app.status != "waiting_for_user":
            raise Conflict(
                "This application is not waiting for answers", code="invalid_state",
                details={"from": app.status, "to": "queued"},
            )  # fmt: skip
        pending = {p["key"]: p for p in app.pending_fields or []}
        unknown = sorted({a.key for a in body.answers if a.key not in pending})
        if unknown:
            raise Invalid(
                "Answers for fields the form did not ask about",
                details={"keys": unknown},
            )
        provided = dict(app.provided_answers or {})
        for a in body.answers:
            p = pending[a.key]
            provided[normalise(p["label"])] = a.value
            if a.remember:
                self.screening.remember(
                    user_id, p["label"], a.value, p.get("field_type") or "other"
                )
        if not self.repos.applications.cas_status(
            app,
            ("waiting_for_user",),
            "queued",
            provided_answers=provided,
            pending_fields=[],
        ):
            self.repos.session.rollback()
            raise Conflict("The application changed", code="invalid_state")
        self.repos.session.commit()
        self._dispatch(app)
        log.info(
            "application answered user=%s app=%s n=%d",
            user_id,
            app.id,
            len(body.answers),
        )
        return self.out(app)

    def cancel(self, user_id: uuid.UUID, app_id: str) -> ApplicationOut:
        app = self._own(user_id, app_id)
        if not self._finish(app, ACTIVE, "cancelled", reason="user_cancelled"):
            raise Conflict(
                f"A {app.status} application cannot be cancelled", code="invalid_state",
                details={"from": app.status, "to": "cancelled"},
            )  # fmt: skip
        return self.out(app)

    # --- state changes (worker and extension) -------------------------------
    def _finish(
        self, app: Application, allowed: tuple[str, ...], to: str, *,
        reason: str | None = None, release: bool = True, **values,
    ) -> bool:  # fmt: skip
        repos = self.repos.applications
        if not repos.cas_status(app, allowed, to, skip_reason=reason, **values):
            self.repos.session.rollback()
            self.repos.session.refresh(app)
            return False
        if release:
            repos.stage_release(app)
        self.repos.jobs.stage_event(
            app.user_id, "application_status",
            {"application_id": app.id, "job_id": app.job_id, "status": to, "reason": reason},
        )  # fmt: skip
        self.repos.session.commit()
        log.info("application %s -> %s reason=%s", app.id, to, reason)
        return True

    def finish_submitted(
        self, app: Application, answers_used: list[dict], shots: list[str]
    ) -> bool:
        now = datetime.now(UTC)
        # "cancelled" is allowed: if the click already happened, the truth wins.
        ok = self.repos.applications.cas_status(
            app, ("running", "cancelled"), "submitted", skip_reason=None,
            submitted_at=now, answers_used=answers_used,
            screenshot_keys=[*(app.screenshot_keys or []), *shots],
        )  # fmt: skip
        if not ok:
            self.repos.session.rollback()
            self.repos.session.refresh(app)
            return False
        self.tracker.mark_applied(app.user_id, app.job_id, now)
        self.repos.jobs.stage_event(
            app.user_id, "job_applied",
            {"job_id": app.job_id, "application_id": app.id, "site": app.site},
        )  # fmt: skip
        self.repos.applications.reset_blocks(app.user_id, app.site)
        self.repos.session.commit()
        log.info("application submitted user=%s app=%s", app.user_id, app.id)
        return True

    def finish_skipped(
        self, app: Application, reason: str, shots: list[str] | None = None
    ) -> bool:
        ok = self._finish(
            app, ACTIVE, "skipped", reason=reason,
            screenshot_keys=[*(app.screenshot_keys or []), *(shots or [])],
        )  # fmt: skip
        if ok and reason in BLOCK_REASONS:
            paused = self.repos.applications.record_block(
                app.user_id, app.site, reason, settings.autopilot_pause_after_blocks
            )
            if paused:
                self.repos.jobs.add_event(
                    app.user_id, "site_paused", {"site": app.site}
                )
                log.warning("site paused user=%s site=%s", app.user_id, app.site)
        return ok

    def finish_failed(
        self, app: Application, reason: str, shots: list[str] | None = None
    ) -> bool:
        return self._finish(
            app, ACTIVE, "failed", reason=reason, error=reason[:200],
            screenshot_keys=[*(app.screenshot_keys or []), *(shots or [])],
        )  # fmt: skip

    def finish_waiting(
        self, app: Application, pending: list[dict], shots: list[str]
    ) -> bool:
        return self._finish(
            app, ("running",), "waiting_for_user", reason="required_field_no_value",
            pending_fields=pending,
            screenshot_keys=[*(app.screenshot_keys or []), *shots],
        )  # fmt: skip

    def defer(self, app: Application, reason: str) -> None:
        """Over a cap: back to the queue untouched (the slot, if any, is returned)."""
        self._finish(app, ("running",), "queued", reason=None)
        log.info("application deferred app=%s scope=%s", app.id, reason)

    # --- extension channel -----------------------------------------------------
    def extension_queue(self, user_id: uuid.UUID) -> list[ApplicationOut]:
        user = self._user(user_id)
        repos = self.repos.applications
        day, hour = local_day(), hour_key()
        paused = set(repos.paused_sites(user_id))
        out = []
        for app in repos.queued("extension", user_id=user_id):
            if app.site in paused or not site_opted_in(user, app.site):
                continue
            if repos.has_room(
                user_id, day, hour, app.site, None, self.caps_for(user, app)
            ):
                continue
            out.append(self.out(app, detail=False))
        return out

    def _ext_app(self, user_id: uuid.UUID, app_id: str) -> Application:
        app = self._own(user_id, app_id)
        if app.channel != "extension":
            raise NotFound("Application not found")
        return app

    def extension_plan(
        self, user_id: uuid.UUID, app_id: str, extra_required: list[str]
    ) -> dict:
        app = self._ext_app(user_id, app_id)
        user = self._user(user_id)
        if app.status not in ("queued", "running"):
            raise Conflict("This application is not open", code="invalid_state")
        refusal = self._refusal(user, "extension", app.site, None)
        if refusal:
            raise ApplyRefused("This application cannot be started", code=refusal)
        try:
            self.repos.applications.reserve(
                app, day=local_day(), hour=hour_key(), caps=self.caps_for(user, app)
            )
        except CapReached as e:
            raise TooManyRequests(
                "Apply cap reached", code="cap_reached", details={"scope": e.scope}
            ) from None
        if app.status == "queued" and self.repos.applications.cas_status(
            app, ("queued",), "running", attempts=app.attempts + 1
        ):
            self.repos.session.commit()
        approval = self.repos.runs.approval_for(user_id, app.run_id)
        run = self.repos.runs.get_for_user(user_id, app.run_id)
        if approval is None or not approval.pdf_key or run is None:
            raise Conflict("No approved PDF", code="run_not_approved")
        profile_row = self.repos.profiles.get_version(user_id, run.profile_version)
        profile = (
            ProfileData.model_validate(profile_row.data)
            if profile_row
            else ProfileData()
        )
        c = profile.contact
        contact = {
            "name": c.name,
            "email": c.email or (user.email if user else None),
            "phone": c.phone,
            "location": c.location,
            "links": c.links,
        }
        ext = self.repos.jobs.extraction_for(user_id, app.job_id)
        jd = JobDescription.model_validate(ext.jd) if ext else None
        answers: dict[str, dict] = {}
        for t in ANSWER_TYPES:
            got = self.screening.answer_for(
                user_id, ScreeningField(label=t.replace("_", " "), field_type=t), jd
            )
            if got:
                answers[t] = got
        for kind in LINK_KINDS:
            got = self.screening.answer_for(
                user_id,
                ScreeningField(label=kind, field_type="link", link_kind=kind),
                jd,
            )
            if got:
                answers[f"link_{kind}"] = got
        required = list(
            dict.fromkeys(
                [*settings.extension_required_fields.get(app.site, []), *extra_required]
            )
        )
        missing = [
            r for r in required
            if (r in CONTACT and not contact.get(r)) or (r in ANSWER_TYPES and r not in answers)
            or (r not in CONTACT and r not in ANSWER_TYPES and r != "resume" and r not in answers)
        ]  # fmt: skip
        return {
            "application_id": app.id,
            "site": app.site,
            "apply_url": app.apply_url,
            "pdf_url": signing.sign(
                approval.pdf_key,
                min(settings.signed_url_ttl_s, 300),
                filename=approval.file_name or "resume.pdf",
            ),
            "file_name": approval.file_name,
            "contact": contact,
            "answers": answers,
            "required_fields": required,
            "required_without_value": missing,
            "skip_if_required_without_value": True,
        }

    def extension_result(
        self, user_id: uuid.UUID, app_id: str, status: str, reason: str | None,
        screenshot_b64: str | None,
    ) -> ApplicationOut:  # fmt: skip
        app = self._ext_app(user_id, app_id)
        target = {"submitted": "submitted", "skipped": "skipped", "error": "failed"}[
            status
        ]
        if app.status == target:
            return self.out(app)  # a retried report
        if app.status != "running":
            raise Conflict(
                "Fetch the apply plan first", code="invalid_state",
                details={"from": app.status, "to": target},
            )  # fmt: skip
        shots: list[str] = []
        if screenshot_b64:
            shots = [self._save_shot(app, screenshot_b64)]
        if status == "submitted":
            used = [
                {
                    "source": "extension",
                    "note": "filled by the paired browser extension",
                }
            ]
            ok = self.finish_submitted(app, used, shots)
        elif status == "skipped":
            ok = self.finish_skipped(
                app, (reason or "skipped_by_extension")[:64], shots
            )
        else:
            ok = self.finish_failed(app, (reason or "extension_error")[:64], shots)
        if not ok:
            raise Conflict("The application changed", code="invalid_state")
        return self.out(app)

    def _save_shot(self, app: Application, b64: str) -> str:
        from app.apply.proof import save_screenshot

        try:
            data = base64.b64decode(b64, validate=True)
        except (binascii.Error, ValueError):
            raise Invalid("screenshot must be base64") from None
        if len(data) > settings.extension_max_screenshot_bytes:
            raise Invalid("screenshot too large")
        if not (data.startswith((b"\x89PNG", b"\xff\xd8\xff"))):
            raise Invalid("screenshot must be a PNG or JPEG")
        return save_screenshot(self.storage, app.user_id, app.id, "extension", data)


__all__ = ["ApplicationService", "autopilot_of"]
