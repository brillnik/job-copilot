"""Autopilot: settings, orchestration (tick / advance) and the daily digest.

No scheduler here: `autopilot_tick` runs after build_recommendations (an event) and from
the CLI/cron; `autopilot_advance` runs when an autopilot run reaches waiting_for_user or
in_review. Everything is idempotent. Logs carry ids and counts only.
"""

import logging
import uuid
from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo

from app.core.clock import local_day
from app.core.config import settings
from app.core.exceptions import AppError, Conflict, NotFound
from app.repositories.manager import RepositoryManager
from app.schemas.autopilot import (
    AutopilotOut,
    AutopilotPut,
    DigestItem,
    DigestOut,
    SiteOptIn,
)
from app.schemas.job import JobDescription, TailorIn
from app.schemas.run import Answer, AnswerIn
from app.services.application import ApplicationService
from app.services.autopilot_prefs import (
    SITES,
    autopilot_enabled,
    autopilot_of,
    site_opted_in,
)
from app.services.prefs import preferences_of

log = logging.getLogger(__name__)


class AckRequired(AppError):
    status_code = 422
    code = "acknowledgement_required"
    detail = "Acknowledge the current policy text to turn this on"


class BadDigestDate(AppError):
    status_code = 422
    code = "validation_error"
    detail = "date must be YYYY-MM-DD"


class AutopilotService:
    def __init__(self, repos: RepositoryManager) -> None:
        self.repos = repos

    # --- settings ----------------------------------------------------------------
    def get(self, user_id: uuid.UUID) -> AutopilotOut:
        user = self.repos.users.get(user_id)
        a = autopilot_of(user)
        paused = self.repos.applications.paused_sites(user_id)
        sites = {}
        for site in SITES:
            e = a["sites_opt_in"].get(site) or {}
            sites[site] = SiteOptIn(
                acknowledged=site_opted_in(user, site),
                acknowledged_at=e.get("acknowledged_at"),
                policy_version=e.get("policy_version"),
                paused=site in paused,
            )
        return AutopilotOut(
            enabled=autopilot_enabled(user),
            min_score=a["min_score"],
            daily_apply_cap=a["daily_apply_cap"],
            digest_time=a["digest_time"],
            sites_opt_in=sites,
            policy_version=settings.autopilot_policy_version,
            acknowledged_version=a["ack_version"],
            paused_sites=paused,
        )

    def put(self, user_id: uuid.UUID, body: AutopilotPut) -> AutopilotOut:
        user = self.repos.users.get(user_id)
        a = autopilot_of(user)
        current = settings.autopilot_policy_version
        if body.enabled:
            if body.acknowledgement_version != current:
                raise AckRequired(details={"policy_version": current})
            a["enabled"], a["ack_version"] = True, current
        elif body.enabled is False:
            a["enabled"] = False
        if body.min_score is not None:
            a["min_score"] = body.min_score
        if body.daily_apply_cap is not None:
            a["daily_apply_cap"] = min(
                body.daily_apply_cap, settings.autopilot_daily_cap_max
            )
        if body.digest_time is not None:
            a["digest_time"] = body.digest_time
        opt = dict(a["sites_opt_in"])
        for site, put in (body.sites or {}).items():
            if put.opt_in:
                if put.acknowledgement_version != current:
                    raise AckRequired(
                        f"Acknowledge the current policy text to opt in to {site}",
                        details={"policy_version": current, "site": site},
                    )
                opt[site] = {
                    "acknowledged_at": datetime.now(UTC).isoformat(),
                    "policy_version": current,
                }
            else:
                opt.pop(site, None)
        a["sites_opt_in"] = opt
        user.autopilot = a
        for site in body.resume_sites or []:
            self.repos.applications.reset_blocks(user_id, site, unpause=True)
        self.repos.session.commit()
        log.info("autopilot settings changed user=%s enabled=%s", user_id, a["enabled"])
        return self.get(user_id)

    # --- digest ----------------------------------------------------------------------
    def digest(self, user_id: uuid.UUID, date: str | None) -> DigestOut:
        tz = ZoneInfo(settings.day_timezone)
        try:
            day = (
                datetime.fromisoformat(date).date() if date else datetime.now(tz).date()
            )
        except ValueError:
            raise BadDigestDate() from None
        start = datetime(day.year, day.month, day.day, tzinfo=tz).astimezone(UTC)
        apps = self.repos.applications.updated_between(
            user_id, start, start + timedelta(days=1)
        )
        jobs = self.repos.runs.jobs_for(user_id, [x.job_id for x in apps])
        out = DigestOut(
            date=day.isoformat(), submitted=[], skipped=[], needs_a_person=[]
        )
        for x in apps:
            j = jobs.get(x.job_id)
            item = DigestItem(
                application_id=x.id, job_id=x.job_id,
                company=j.company if j else None, title=j.title if j else None,
                status=x.status, reason=x.skip_reason or x.error, direct_link=x.apply_url,
            )  # fmt: skip
            if x.status == "submitted":
                item.direct_link = None
                out.submitted.append(item)
            elif x.status == "skipped":
                out.skipped.append(item)
            elif x.status in ("waiting_for_user", "failed"):
                out.needs_a_person.append(item)
        return out


# --- orchestration (tasks) -------------------------------------------------------------
def _services(ctx, repos: RepositoryManager):
    from app.services.job import JobService
    from app.services.profile import ProfileService
    from app.services.run import RunService

    jobs = JobService(repos, ctx.queue, ctx.storage)
    profiles = ProfileService(repos, None, None, ctx.embedder, ctx.queue)
    runs = RunService(repos, ctx.queue, ctx.storage, jobs, profiles)
    apps = ApplicationService(repos, ctx.queue, ctx.storage)
    return jobs, runs, apps


def autopilot_tick(ctx, user_id: uuid.UUID | str) -> dict[str, int]:
    """Save good recommendations, start tailoring within the daily run cap, and move
    waiting/in-review autopilot runs forward."""
    from app.services.recommendation import RecommendationService, ScoringContext

    user_id = uuid.UUID(str(user_id))
    stats = {"saved": 0, "tailored": 0, "advanced": 0}
    with ctx.session_factory() as session:
        repos = RepositoryManager(session)
        user = repos.users.get(user_id)
        if user is None or user.status != "active" or not autopilot_enabled(user):
            return stats
        ap = autopilot_of(user)
        prefs = preferences_of(user)
        jobs, _, _ = _services(ctx, repos)
        rec_svc = RecommendationService(
            repos, ctx.queue, ScoringContext(scoring=ctx.scoring, embedder=ctx.embedder)
        )
        # 1. save: score >= min_score, no red flags, filters pass
        for rec in repos.recommendations.digest(user_id, local_day()):
            if stats["saved"] >= settings.autopilot_max_saves_per_tick:
                break
            if rec.action != "none" or rec.score < ap["min_score"]:
                continue
            cat = repos.catalog.by_id(rec.catalog_job_id)
            if cat is None or cat.closed_at is not None or not cat.jd:
                continue
            if JobDescription.model_validate(cat.jd).red_flags:
                continue
            if prefs.cities and not (cat.remote or cat.city in prefs.cities):
                continue
            try:
                rec_svc.save(user_id, rec.id)
                stats["saved"] += 1
            except AppError:
                continue
        # 2. tailor saved jobs while the daily run cap allows
        for job in repos.applications.untailored_recommended_jobs(
            user_id, ap["min_score"]
        ):
            if job.red_flags:
                continue
            try:
                jobs.tailor(user_id, job.id, TailorIn(), autopilot=True)
                stats["tailored"] += 1
            except AppError as e:
                if e.code == "daily_cap":
                    break
                continue
        # 3. move runs that are waiting or ready
        for run in repos.applications.autopilot_runs(
            user_id, ("waiting_for_user", "in_review")
        ):
            if _advance(ctx, repos, user_id, run.id):
                stats["advanced"] += 1
    log.info("autopilot tick user=%s %s", user_id, stats)
    return stats


def autopilot_advance(ctx, user_id: uuid.UUID | str, run_id: str) -> bool:
    user_id = uuid.UUID(str(user_id))
    with ctx.session_factory() as session:
        repos = RepositoryManager(session)
        return _advance(ctx, repos, user_id, run_id)


def _advance(ctx, repos: RepositoryManager, user_id: uuid.UUID, run_id: str) -> bool:
    user = repos.users.get(user_id)
    run = repos.runs.get_for_user(user_id, run_id)
    if user is None or run is None or not run.autopilot or not autopilot_enabled(user):
        return False
    _, runs, apps = _services(ctx, repos)
    if run.status == "waiting_for_user":
        # ask_user in Autopilot: "not in profile", answered automatically, no interrupt
        body = AnswerIn(
            answers=[
                Answer(skill=q["skill"], answer="no")
                for q in (run.pending_questions or [])
            ]
        )
        if not body.answers:
            return False
        try:
            runs.answer(user_id, run_id, body)
        except AppError:
            return False
        return True
    if run.status != "in_review":
        return False
    draft = repos.runs.latest_draft(user_id, run_id)
    if draft is None:
        return False
    target = preferences_of(user).coverage_target
    clean = (
        not run.flagged
        and not draft.violations
        and (draft.coverage or {}).get("pct", 0.0) >= target
        and (not run.max_pages or (draft.pages or {}).get("count", 1) <= run.max_pages)
    )
    if not clean:
        apps.record_skipped_run(user_id, run_id, "draft_flagged")
        log.info("autopilot flagged draft not applied run=%s", run_id)
        return True
    if not draft.pdf_key:
        from app.tasks import runs as run_tasks

        run_tasks.render_pdf(ctx, user_id, run_id, draft.iteration)
        repos.session.refresh(draft)
        if not draft.pdf_key:
            return False
    try:
        runs.approve(user_id, run_id)
        apps.create_for_run(user_id, run_id, mode="autopilot")
    except (Conflict, NotFound) as e:
        log.info("autopilot approve/apply stopped run=%s code=%s", run_id, e.code)
        return False
    return True


def send_digests(ctx, now: datetime | None = None) -> int:
    """For every Autopilot user whose digest_time has passed today and who has not
    had today's digest: send it (LogMailer until a provider is wired). Run every few
    minutes from cron."""
    now = now or datetime.now(UTC)
    local = now.astimezone(ZoneInfo(settings.day_timezone))
    today = local.date().isoformat()
    sent = 0
    with ctx.session_factory() as session:
        repos = RepositoryManager(session)
        for uid in repos.applications.autopilot_user_ids():
            user = repos.users.get(uid)
            a = autopilot_of(user)
            if not autopilot_enabled(user) or a["last_digest_date"] == today:
                continue
            if local.strftime("%H:%M") < a["digest_time"]:
                continue
            d = AutopilotService(repos).digest(uid, today)
            if ctx.mailer is not None:
                ctx.mailer.send(
                    str(uid), "autopilot_digest", date=today,
                    submitted=str(len(d.submitted)), skipped=str(len(d.skipped)),
                    needs_a_person=str(len(d.needs_a_person)),
                )  # fmt: skip
            user.autopilot = {**(user.autopilot or {}), "last_digest_date": today}
            session.commit()
            sent += 1
    log.info("digests sent=%d", sent)
    return sent
