import pytest

from app.models.job import Job
from app.repositories.job import RunInProgress
from app.repositories.manager import RepositoryManager
from app.services.run_state import TERMINAL, TRANSITIONS, IllegalTransition, transition
from tests.jobs_helpers import make_user
from tests.runs_helpers import run_ready

ALLOWED = {
    ("queued", "running"), ("queued", "cancelled"), ("queued", "needs_attention"),
    ("running", "waiting_for_user"), ("running", "in_review"),
    ("running", "needs_attention"), ("running", "cancelled"),
    ("waiting_for_user", "queued"), ("waiting_for_user", "cancelled"),
    ("in_review", "approved"), ("in_review", "rejected"),
}  # fmt: skip
STATUSES = list(TRANSITIONS)


def test_table_is_exactly_the_documented_one():
    assert {(a, b) for a, tos in TRANSITIONS.items() for b in tos} == ALLOWED
    assert all(not TRANSITIONS[s] for s in TERMINAL)


@pytest.mark.parametrize("frm", STATUSES)
@pytest.mark.parametrize("to", STATUSES)
def test_every_pair(db_session, tmp_path, frm, to):
    user = make_user(db_session)
    run = run_ready(db_session, tmp_path, user, status=frm)
    repos = RepositoryManager(db_session)
    events_before = run.event_seq
    if (frm, to) in ALLOWED:
        transition(repos, run, to)
        assert run.status == to
        # an event is appended, with the next seq, for every change
        evs = repos.runs.events_after(user.id, run.id, events_before)
        assert [e.type for e in evs] == ["status"] and evs[0].payload["status"] == to
        assert evs[0].seq == events_before + 1
    else:
        with pytest.raises(IllegalTransition):
            transition(repos, run, to)
        assert run.status == frm and run.event_seq == events_before


def test_losing_a_race_changes_nothing(db_session, tmp_path):
    user = make_user(db_session)
    run = run_ready(db_session, tmp_path, user, status="queued")
    repos = RepositoryManager(db_session)
    stale = repos.runs.get_for_user(user.id, run.id)
    # someone else cancels between our read and our write
    db_session.execute(
        __import__("sqlalchemy").text("UPDATE agent_runs SET status='cancelled'")
    )
    db_session.commit()
    with pytest.raises(IllegalTransition) as e:
        transition(repos, stale, "running")
    assert e.value.details["from"] == "cancelled"


def test_job_status_follows_the_run(db_session, tmp_path):
    user = make_user(db_session)
    run = run_ready(db_session, tmp_path, user, status="queued")
    repos = RepositoryManager(db_session)
    job = db_session.get(Job, run.job_id)
    assert job.status == "tailoring"
    transition(repos, run, "cancelled")
    db_session.refresh(job)
    assert job.status == "new"


def test_second_active_run_for_a_job_is_refused(db_session, tmp_path):
    user = make_user(db_session)
    run = run_ready(db_session, tmp_path, user, status="waiting_for_user")
    job = db_session.get(Job, run.job_id)
    with pytest.raises(RunInProgress):
        RepositoryManager(db_session).jobs.reserve_run(
            user.id, job, 1, "2026-01-01", 50
        )
