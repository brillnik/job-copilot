"""run_application: the apply task. Idempotent: only a `queued` application is taken.

Order: kill switches -> claim (queued -> running) -> atomic cap slots -> browser graph
-> record the outcome (submitted / skipped / waiting / failed). Failures and skips give
their cap slot back; only submitted applications count against the caps.
"""

import logging
import random
import re
import tempfile
import time
import uuid
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from app.ai.embeddings import Embedder
from app.apply.adapters import default_adapters
from app.apply.adapters.base import FormAdapter
from app.apply.drivers import BrowserDriver
from app.apply.fallback import ConservativeFallback, FormFallback
from app.apply.graph import ApplyJob, run_graph
from app.apply.mapping import Mapper, approved_pdf_file, intended_report
from app.apply.policy import BlockedTarget, HostPolicy
from app.core.clock import local_day
from app.core.config import settings
from app.repositories.application import CapReached
from app.repositories.manager import RepositoryManager
from app.schemas.job import JobDescription
from app.schemas.profile import ProfileData
from app.services.application import ApplicationService, hour_key
from app.services.screening import ScreeningLLM, ScreeningService
from app.storage.base import Storage
from app.tasks.queue import TaskQueue

log = logging.getLogger(__name__)


@dataclass
class ApplyContext:
    session_factory: Callable[[], Any]
    storage: Storage
    driver: BrowserDriver
    embedder: Embedder | None = None
    adapters: list[FormAdapter] = field(default_factory=default_adapters)
    fallback: FormFallback | None = field(default_factory=ConservativeFallback)
    llm: ScreeningLLM | None = None
    queue: TaskQueue | None = None
    sleep: Callable[[float], None] = time.sleep
    rng: random.Random = field(default_factory=random.Random)
    paces: list[float] = field(default_factory=list)  # what we waited (for tests)

    def pace(self) -> None:
        lo, hi = settings.autopilot_pacing_ms
        ms = self.rng.uniform(lo, max(lo, hi))
        self.paces.append(ms)
        self.sleep(ms / 1000)


def _safe_name(name: str | None) -> str:
    return re.sub(r"[^A-Za-z0-9._-]", "_", name or "resume.pdf")[:120] or "resume.pdf"


def run_application(
    ctx: ApplyContext, user_id: uuid.UUID | str, application_id: str
) -> str | None:
    """Returns the resulting status (None if nothing was done)."""
    user_id = uuid.UUID(str(user_id))
    with ctx.session_factory() as session:
        repos = RepositoryManager(session)
        user = repos.users.get(user_id)
        if user is None or user.status != "active":
            return None
        app = repos.applications.get_for_user(user_id, application_id)
        if app is None or app.status != "queued" or app.channel != "playwright":
            log.info(
                "apply skipped app=%s status=%s", application_id, app and app.status
            )
            return None
        svc = ApplicationService(
            repos,
            ctx.queue,
            ctx.storage,
            ScreeningService(repos, ctx.embedder, ctx.llm),
        )
        if not repos.applications.cas_status(
            app, ("queued",), "running", attempts=app.attempts + 1
        ):
            return None  # another worker claimed it
        session.commit()

        refusal = svc._refusal(user, "playwright", app.site, app.ats)
        if refusal:
            svc.finish_skipped(app, refusal)
            return app.status
        try:
            repos.applications.reserve(
                app, day=local_day(), hour=hour_key(), caps=svc.caps_for(user, app)
            )
        except CapReached as e:
            svc.defer(app, e.scope)
            return app.status

        run = repos.runs.get_for_user(user_id, app.run_id)
        approval = repos.runs.approval_for(user_id, app.run_id)
        job_row = repos.jobs.get_for_user(user_id, app.job_id)
        profile_row = (
            repos.profiles.get_version(user_id, run.profile_version) if run else None
        )
        if not (run and approval and approval.pdf_key and approval.decision == "approved"
                and job_row and profile_row):  # fmt: skip
            svc.finish_failed(app, "missing_input")
            return app.status
        try:
            policy = HostPolicy.for_target(app.apply_url)
        except BlockedTarget as e:
            svc.finish_skipped(app, e.reason)
            return app.status
        ext = repos.jobs.extraction_for(user_id, app.job_id)
        jd = JobDescription.model_validate(ext.jd) if ext else None

        def on_detect(name: str) -> str | None:
            if name == "generic" or app.slot_hour:
                return None
            try:
                repos.applications.reserve_ats(
                    app, name, hour_key(), settings.autopilot_ats_hourly_cap
                )
            except CapReached as e:
                return e.scope
            return None

        with tempfile.TemporaryDirectory(prefix="jc-apply-") as tmp:
            approved = approved_pdf_file(
                Path(tmp),
                _safe_name(approval.file_name),
                ctx.storage.read(approval.pdf_key),
            )
            mapper = Mapper(
                user_id,
                ScreeningService(repos, ctx.embedder, ctx.llm),
                ProfileData.model_validate(profile_row.data),
                user.email,
                jd,
                dict(app.provided_answers or {}),
                approved,
            )
            try:
                with ctx.driver.session(policy) as page:
                    job = ApplyJob(
                        user_id=user_id, application_id=app.id, apply_url=app.apply_url,
                        page=page, policy=policy, adapters=ctx.adapters, mapper=mapper,
                        approved=approved, fallback=ctx.fallback, storage=ctx.storage,
                        pace=ctx.pace,
                        should_stop=lambda: repos.applications.status_of(user_id, app.id)
                        != "running",
                        enabled_ats=settings.apply_enabled_ats, on_detect=on_detect,
                    )  # fmt: skip
                    outcome = run_graph(job)
                    plan = job.plan
                    shots = job.shots
            except Exception as e:  # noqa: BLE001 - browser could not even start
                log.error(
                    "apply browser failed app=%s error=%s", app.id, type(e).__name__
                )
                svc.finish_failed(app, f"browser_unavailable:{type(e).__name__}")
                return app.status

        k, reason = outcome.kind, outcome.reason
        if k == "submitted":
            svc.finish_submitted(app, intended_report(plan), shots)
        elif k == "blocked" or k == "skipped":
            svc.finish_skipped(app, reason, shots)
        elif k == "unmapped":
            if app.mode == "manual":
                svc.finish_waiting(app, outcome.pending, shots)
            else:
                svc.finish_skipped(app, reason, shots)
        elif k == "deferred":
            svc.defer(app, reason)
        elif k == "cancelled":
            log.info("apply cancelled app=%s", app.id)
        else:
            svc.finish_failed(app, reason or "failed", shots)
        session.refresh(app)
        return app.status
