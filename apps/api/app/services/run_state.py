"""The ONE place a run's status changes.

Every change: checks the transitions table, moves the row with a compare-and-set (so
two racing callers cannot both win), keeps the job's status in step, appends a run
event, adds a user-level event, and gives the daily-cap slot back when a run ends
without producing work (cancelled, needs_attention).
"""

import logging
from typing import Any

from app.core.clock import local_day
from app.core.exceptions import Conflict
from app.models.job import AgentRun
from app.repositories.manager import RepositoryManager

log = logging.getLogger(__name__)

TRANSITIONS: dict[str, frozenset[str]] = {
    "queued": frozenset({"running", "cancelled", "needs_attention"}),
    "running": frozenset(
        {"waiting_for_user", "in_review", "needs_attention", "cancelled"}
    ),
    "waiting_for_user": frozenset({"queued", "cancelled"}),
    "in_review": frozenset({"approved", "rejected"}),
    "approved": frozenset(),
    "rejected": frozenset(),
    "needs_attention": frozenset(),
    "cancelled": frozenset(),
}
TERMINAL = frozenset({"approved", "rejected", "needs_attention", "cancelled"})
# Ends without a usable result: the run's daily-cap slot is returned.
REFUNDED = frozenset({"cancelled", "needs_attention"})
JOB_STATUS = {
    "queued": "tailoring",
    "running": "tailoring",
    "waiting_for_user": "tailoring",
    "in_review": "in_review",
    "approved": "approved",
    "rejected": "rejected",
    "cancelled": "new",
    "needs_attention": "new",
}


class IllegalTransition(Conflict):
    code = "invalid_state"
    detail = "This run cannot change to that status"


def transition(
    repos: RepositoryManager,
    run: AgentRun,
    to: str,
    *,
    reason: str | None = None,
    step: str | None = None,
    payload: dict[str, Any] | None = None,
    sync_job: bool = True,
    commit: bool = True,
) -> AgentRun:
    """Move `run` to `to`. With commit=False the caller owns the transaction.

    sync_job=False leaves the job alone (a superseded run must not clobber the
    status its replacement just set).
    """
    session = repos.session
    frm = run.status
    allowed = TRANSITIONS.get(frm, frozenset())
    if to not in allowed:
        log.info("run %s illegal transition %s -> %s", run.id, frm, to)
        raise IllegalTransition(
            f"A run that is {frm} cannot become {to}",
            details={"from": frm, "to": to},
        )
    if not repos.runs.stage_cas_status(run, to, reason, step):
        # Someone else moved it first. Report what it is now, change nothing.
        session.rollback()
        session.refresh(run)
        log.info(
            "run %s lost transition race %s -> %s now=%s", run.id, frm, to, run.status
        )
        raise IllegalTransition(
            f"The run is now {run.status}",
            details={"from": run.status, "to": to},
        )
    session.refresh(run)

    job = repos.jobs.get_for_user(run.user_id, run.job_id)
    if sync_job and job is not None and job.status != "archived":
        job.status = JOB_STATUS[to]
    if to in REFUNDED:
        repos.runs.stage_release_quota(run.user_id, local_day(run.created_at))

    body = {"status": to, "from": frm, "reason": reason, **(payload or {})}
    repos.runs.stage_event(run, "status", body)
    repos.jobs.stage_event(
        run.user_id,
        "run_status",
        {"run_id": run.id, "job_id": run.job_id, "status": to},
    )
    if commit:
        session.commit()
    log.info("run %s %s -> %s%s", run.id, frm, to, f" ({reason})" if reason else "")
    return run
