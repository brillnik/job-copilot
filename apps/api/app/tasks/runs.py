"""Background tasks for runs. Each takes user_id explicitly and re-checks ownership.

Logs carry ids, statuses and counts only: never resume text or contact details.
"""

import logging
import uuid

from app.agent.pdf import render
from app.agent.tailor import AgentInput, AgentResult
from app.ai.errors import TransientError
from app.core.config import settings
from app.core.exceptions import AppError
from app.models.run import Draft
from app.repositories.manager import RepositoryManager
from app.schemas.job import JobDescription
from app.schemas.profile import ProfileData
from app.schemas.run import TailoredResume
from app.services.prefs import preferences_of
from app.services.run_state import IllegalTransition, transition
from app.tasks.jobs import TaskContext

log = logging.getLogger(__name__)


def draft_pdf_key(user_id: uuid.UUID, run_id: str, iteration: int, rev: int) -> str:
    return f"users/{user_id.hex}/drafts/{run_id}/{iteration}-{rev}.pdf"


def _active(repos: RepositoryManager, user_id: uuid.UUID) -> bool:
    user = repos.users.get(user_id)
    return user is not None and user.status == "active"


def _flagged(result: AgentResult, max_pages: int | None, target: float) -> bool:
    if not result.drafts:
        return True
    last = result.drafts[-1]
    too_long = max_pages is not None and last.pages.count > max_pages
    return bool(last.violations) or last.coverage.pct < target or too_long


def tailor(
    ctx: TaskContext, user_id: uuid.UUID | str, run_id: str, resume: bool = False
) -> None:
    """Run the agent for one run. `resume=True` continues after the user's answers."""
    user_id = uuid.UUID(str(user_id))
    with ctx.session_factory() as session:
        repos = RepositoryManager(session)
        if not _active(repos, user_id):
            return  # the account is being deleted
        run = repos.runs.get_for_user(user_id, run_id)
        if run is None or run.status != "queued":
            log.info("tailor skipped run=%s status=%s", run_id, run and run.status)
            return  # cancelled (or already handled) while it waited in the queue
        if ctx.agent is None:
            # TODO: the tailoring agent is not built yet. The run stays queued, pinned
            # to its profile_version, until one is wired in tasks/runtime.py.
            log.info(
                "tailor stub run=%s profile_version=%s", run.id, run.profile_version
            )
            return
        try:
            transition(repos, run, "running", step="starting")
        except IllegalTransition:
            return

        profile = repos.profiles.get_version(user_id, run.profile_version)
        ext = repos.jobs.extraction_for(user_id, run.job_id)
        if profile is None or ext is None:
            transition(repos, run, "needs_attention", reason="missing_input")
            return
        prefs = preferences_of(repos.users.get(user_id))

        def progress(step: str, payload: dict) -> None:
            repos.runs.stage_event(run, "step", {"step": step, **payload})
            session.commit()

        inp = AgentInput(
            run_id=run.id,
            jd=JobDescription.model_validate(ext.jd),
            profile=ProfileData.model_validate(profile.data),
            profile_version=run.profile_version,
            answers=repos.runs.answers_full(user_id),
            max_pages=run.max_pages,
            guidance=run.guidance,
            first_iteration=run.iteration + 1,
            max_iterations=settings.max_tailor_iterations,
            coverage_target=prefs.coverage_target,
            user_id=str(user_id),
            progress=progress,
        )

        def should_stop() -> bool:  # cancel lands at the next step boundary
            return repos.runs.status_of(user_id, run.id) != "running"

        try:
            result = ctx.agent.run(inp, should_stop)
        except TransientError:
            log.error("tailor LLM unreachable run=%s", run.id)
            _finish(repos, run, "needs_attention", reason="llm_unreachable")
            return
        except Exception as e:  # noqa: BLE001 - a task must never die silently
            log.error("tailor crashed run=%s error=%s", run.id, type(e).__name__)
            _finish(repos, run, "needs_attention", reason="agent_error")
            return
        if should_stop():
            log.info("tailor stopped run=%s status=%s", run.id, run.status)
            return

        run.cost_usd += result.cost_usd
        run.models = result.models or run.models
        run.prompt_version = result.prompt_version or run.prompt_version
        if result.questions:
            run.pending_questions = [q.model_dump() for q in result.questions]
            if _finish(repos, run, "waiting_for_user", step="asking"):
                if run.autopilot and ctx.queue is not None:
                    ctx.queue.enqueue(
                        "autopilot_advance", user_id=str(user_id), run_id=run.id
                    )
                log.info(
                    "tailor waiting run=%s questions=%d", run.id, len(result.questions)
                )
            return

        iteration = run.iteration
        saved: list[Draft] = []
        for d in result.drafts:
            iteration += 1
            saved.append(
                repos.runs.stage_save_draft(
                    Draft(
                        run_id=run.id,
                        user_id=user_id,
                        iteration=iteration,
                        tailored=d.tailored.model_dump(),
                        violations=[v.model_dump() for v in d.violations],
                        coverage=d.coverage.model_dump(),
                        pages=d.pages.model_dump(),
                        outcome=d.outcome,
                    )
                )
            )
        run.iteration = iteration
        run.flagged = _flagged(result, run.max_pages, inp.coverage_target)
        if _finish(repos, run, "in_review", step="review"):
            if saved and ctx.queue is not None:
                ctx.queue.enqueue(
                    "render_pdf",
                    user_id=str(user_id),
                    run_id=run.id,
                    iteration=saved[-1].iteration,
                )
            if run.autopilot and ctx.queue is not None:
                ctx.queue.enqueue(
                    "autopilot_advance", user_id=str(user_id), run_id=run.id
                )
            log.info(
                "tailor done run=%s drafts=%d flagged=%s",
                run.id,
                len(saved),
                run.flagged,
            )


def _finish(repos, run, to: str, **kw) -> bool:
    """Final transition; False if the run was cancelled meanwhile (result dropped)."""
    try:
        transition(repos, run, to, **kw)
        return True
    except IllegalTransition:
        repos.session.rollback()
        log.info("tailor result dropped run=%s now=%s", run.id, run.status)
        return False
    except AppError:
        repos.session.rollback()
        raise


def render_pdf(
    ctx: TaskContext,
    user_id: uuid.UUID | str,
    run_id: str,
    iteration: int | None = None,
) -> None:
    """Render a draft to PDF. Drops its own result if the draft was edited meanwhile."""
    user_id = uuid.UUID(str(user_id))
    with ctx.session_factory() as session:
        repos = RepositoryManager(session)
        if not _active(repos, user_id):
            return
        run = repos.runs.get_for_user(user_id, run_id)
        if run is None:
            return
        draft = repos.runs.latest_draft(user_id, run_id)
        if draft is None or (iteration is not None and draft.iteration != iteration):
            return
        profile = repos.profiles.get_version(user_id, run.profile_version)
        if profile is None:
            return
        rev = draft.rev
        pdf, pages = render(
            ProfileData.model_validate(profile.data),
            TailoredResume.model_validate(draft.tailored),
        )
        session.refresh(draft)
        if draft.rev != rev:
            log.info(
                "render_pdf stale run=%s draft=%s; a newer render follows",
                run_id,
                draft.id,
            )
            return
        key = draft_pdf_key(user_id, run_id, draft.iteration, rev)
        ctx.storage.save(key, pdf)
        old, draft.pdf_key, draft.pages = draft.pdf_key, key, pages.model_dump()
        repos.runs.stage_event(
            run, "pdf", {"iteration": draft.iteration, "pages": pages.count}
        )
        session.commit()
        if old and old != key:
            ctx.storage.delete(old)
        log.info(
            "render_pdf done run=%s draft=%s pages=%d", run_id, draft.id, pages.count
        )
