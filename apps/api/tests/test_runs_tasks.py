import pytest
from sqlalchemy import select

from app.agent.tailor import AgentResult, DraftResult
from app.models.job import Job, RunQuota
from app.models.run import Draft
from app.repositories.manager import RepositoryManager
from app.schemas.run import Coverage, Pages, Violation
from app.services.run_state import transition
from app.tasks import runs as run_tasks
from app.tasks.queue import RecordingQueue
from tests.jobs_helpers import make_ctx, make_user
from tests.runs_helpers import FakeAgent, ask, run_ready, tailored, unreachable


@pytest.fixture
def user(db_session):
    return make_user(db_session)


def go(db, tmp_path, user, run, agent, **kw):
    queue = RecordingQueue()
    ctx = make_ctx(db, tmp_path, agent=agent, queue=queue)
    run_tasks.tailor(ctx, user.id, run.id, **kw)
    db.refresh(run)
    return queue


def test_without_an_agent_the_run_stays_queued(db_session, tmp_path, user):
    run = run_ready(db_session, tmp_path, user, status="queued")
    go(db_session, tmp_path, user, run, None)
    assert run.status == "queued"


def test_a_clean_result_ends_in_review_and_renders(db_session, tmp_path, user):
    run = run_ready(db_session, tmp_path, user, status="queued")
    agent = FakeAgent()
    queue = go(db_session, tmp_path, user, run, agent)
    assert (run.status, run.flagged, run.iteration, run.current_step) == (
        "in_review",
        False,
        1,
        "review",
    )
    (draft,) = db_session.scalars(select(Draft)).all()
    assert draft.iteration == 1 and draft.outcome == "done"
    assert queue.calls == [
        ("render_pdf", {"user_id": str(user.id), "run_id": run.id, "iteration": 1})
    ]
    assert db_session.get(Job, run.job_id).status == "in_review"
    inp = agent.inputs[0]  # pinned to the run's profile version, not "latest"
    assert (inp.profile_version, inp.first_iteration, inp.coverage_target) == (
        1,
        1,
        0.6,
    )


@pytest.mark.parametrize(
    "draft",
    [
        DraftResult(
            tailored(),
            violations=[Violation(code="invented_number", field="bullet", message="x")],
            coverage=Coverage(pct=1.0),
        ),
        DraftResult(
            tailored(), coverage=Coverage(covered=["a"], missing=["b", "c"], pct=0.33)
        ),
        DraftResult(tailored(), coverage=Coverage(pct=1.0), pages=Pages(count=3)),
    ],
    ids=["fact-check", "coverage", "page-fit"],
)
def test_checks_still_failing_after_the_last_iteration_flag_the_run(
    db_session, tmp_path, user, draft
):
    run = run_ready(db_session, tmp_path, user, status="queued", max_pages=2)
    go(db_session, tmp_path, user, run, FakeAgent(AgentResult(drafts=[draft])))
    assert (run.status, run.flagged) == ("in_review", True)  # always lands in review


def test_questions_pause_the_run(db_session, tmp_path, user):
    run = run_ready(db_session, tmp_path, user, status="queued")
    go(db_session, tmp_path, user, run, FakeAgent(ask("Kubernetes")))
    assert run.status == "waiting_for_user"
    assert run.pending_questions == [{"skill": "Kubernetes", "prompt": None}]
    assert db_session.scalars(select(Draft)).all() == []


def test_unreachable_llm_is_needs_attention_and_free(db_session, tmp_path, user):
    run = run_ready(db_session, tmp_path, user, status="queued")
    go(db_session, tmp_path, user, run, FakeAgent(error=unreachable))
    assert (run.status, run.status_reason) == ("needs_attention", "llm_unreachable")
    assert db_session.scalar(select(RunQuota.used)) == 0
    assert db_session.get(Job, run.job_id).status == "new"


def test_a_crash_is_needs_attention_too(db_session, tmp_path, user):
    run = run_ready(db_session, tmp_path, user, status="queued")
    go(db_session, tmp_path, user, run, FakeAgent(error=ValueError("boom")))
    assert (run.status, run.status_reason) == ("needs_attention", "agent_error")


def test_cancel_while_the_agent_works_drops_its_result(db_session, tmp_path, user):
    run = run_ready(db_session, tmp_path, user, status="queued")
    agent = FakeAgent()
    agent.on_run = lambda: transition(RepositoryManager(db_session), run, "cancelled")
    queue = go(db_session, tmp_path, user, run, agent)
    assert run.status == "cancelled" and queue.calls == []
    assert db_session.scalars(select(Draft)).all() == []
    assert db_session.scalar(select(RunQuota.used)) == 0


def test_a_run_cancelled_in_the_queue_is_skipped(db_session, tmp_path, user):
    run = run_ready(db_session, tmp_path, user, status="queued")
    transition(RepositoryManager(db_session), run, "cancelled")
    agent = FakeAgent()
    go(db_session, tmp_path, user, run, agent)
    assert agent.inputs == [] and run.status == "cancelled"


def test_resume_numbers_iterations_on_and_sees_the_answers(db_session, tmp_path, user):
    run = run_ready(
        db_session, tmp_path, user, status="in_review"
    )  # iteration 1 exists
    run.iteration = 1
    from app.models.job import UserAnswer

    db_session.add(
        UserAnswer(user_id=user.id, skill="kubernetes", answer="yes", detail="EKS")
    )
    db_session.commit()
    # a fresh waiting run on the same pinned profile
    run2 = run_ready(db_session, tmp_path, user, status="waiting_for_user")
    transition(RepositoryManager(db_session), run2, "queued")
    agent = FakeAgent()
    go(db_session, tmp_path, user, run2, agent, resume=True)
    assert agent.inputs[0].answers == [("kubernetes", "yes", "EKS")]
    assert run2.status == "in_review"


# --- render_pdf --------------------------------------------------------------
def test_render_pdf_stores_a_pdf_and_page_stats(db_session, tmp_path, user):
    run = run_ready(db_session, tmp_path, user)
    draft = db_session.scalar(select(Draft))
    assert draft.pdf_key == f"users/{user.id.hex}/drafts/{run.id}/1-1.pdf"
    assert (tmp_path / draft.pdf_key).read_bytes().startswith(b"%PDF")
    assert draft.pages["count"] == 1


def test_a_render_of_an_edited_draft_is_dropped(
    db_session, tmp_path, user, monkeypatch
):
    run = run_ready(db_session, tmp_path, user, render=False)
    draft = db_session.scalar(select(Draft))
    real = run_tasks.render

    def render_then_edit(*a):
        out = real(*a)
        draft.rev += 1  # the user saved an edit while we rendered
        db_session.commit()
        return out

    monkeypatch.setattr(run_tasks, "render", render_then_edit)
    run_tasks.render_pdf(make_ctx(db_session, tmp_path), user.id, run.id)
    db_session.refresh(draft)
    assert draft.pdf_key is None
    assert not any(tmp_path.rglob("*.pdf"))
