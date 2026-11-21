import pytest
from sqlalchemy import select

from app.agent.fact_check import build_facts, fact_check
from app.agent.graph import GraphTailorAgent, build_graph, open_checkpointer
from app.agent.pipeline import STEPS, Ctx, run_pipeline
from app.ai.errors import TransientError
from app.models.run import RunEvent
from app.tasks import runs as run_tasks
from tests.agent_helpers import FakeLLM, bad_write, good_write, make_deps, make_input
from tests.jobs_helpers import make_ctx, make_user
from tests.runs_helpers import PROFILE, run_ready


def both(tmp_path, llm_factory, **inp_over):
    """Run the reference pipeline and the graph on identical inputs."""
    ev_p, ev_g = [], []
    res_p = run_pipeline(make_input(events=ev_p, **inp_over), make_deps(llm_factory()))
    agent = GraphTailorAgent(make_deps(llm_factory()), path=str(tmp_path / "ck.db"))
    res_g = agent.run(make_input(events=ev_g, **inp_over), lambda: False)
    return (res_p, ev_p), (res_g, ev_g)


def dump(res):
    return (
        [d.__dict__ | {k: getattr(d, k).model_dump() for k in ("tailored", "coverage", "pages")}
         | {"violations": [v.model_dump() for v in d.violations]} for d in res.drafts],
        [q.model_dump() for q in res.questions],
        round(res.cost_usd, 6), res.models, res.prompt_version,
    )  # fmt: skip


def test_parity_clean_run(tmp_path):
    (rp, ep), (rg, eg) = both(tmp_path, FakeLLM)
    assert dump(rp) == dump(rg) and ep == eg
    assert [s for s, _ in ep] == list(STEPS)
    (d,) = rg.drafts
    assert (
        d.violations == []
        and d.coverage.pct == 1.0
        and rg.models == {"tailor": "fake-llm"}
    )


def test_parity_with_retry_and_feedback(tmp_path):
    def factory():
        return FakeLLM(writes=[bad_write(), good_write(make_bullets())])

    (rp, ep), (rg, eg) = both(tmp_path, factory)
    assert dump(rp) == dump(rg) and ep == eg
    assert [bool(d.violations) for d in rg.drafts] == [True, False]
    assert [s for s, _ in ep].count("write_draft") == 2
    assert [p["iteration"] for s, p in ep if s == "write_draft"] == [1, 2]


def make_bullets():
    from app.agent.llm import Bullet

    return [Bullet("b1", "Built Kafka pipelines processing 2M events a day"),
            Bullet("b2", "Led the migration of Postgres to Aurora")]  # fmt: skip


def test_retry_feedback_reaches_the_llm_and_cap_reverts_to_profile_text(tmp_path):
    llm = FakeLLM(writes=[bad_write()])  # never improves
    res = run_pipeline(make_input(max_iterations=2), make_deps(llm))
    assert len(res.drafts) == 2 and len(llm.write_calls) == 2
    assert {v.code for v in llm.write_calls[1][2]} >= {
        "invented_number",
        "unsupported_skill",
    }
    first, last = res.drafts
    assert first.violations  # kept for the user to see
    assert last.violations == [] and "reverted" in last.outcome
    assert all(b.reverted for b in last.tailored.bullets if b.source_id == "b1")
    assert last.tailored.summary is None
    # whatever is returned last passes the code fact check
    facts = build_facts(PROFILE, [])
    assert fact_check(facts, last.tailored) == []


def test_unknown_source_is_dropped_not_kept(tmp_path):
    w = good_write(make_bullets())
    w.bullets[0].source_id = "ghost"
    res = run_pipeline(make_input(max_iterations=1), make_deps(FakeLLM(writes=[w])))
    assert [b.source_id for b in res.drafts[-1].tailored.bullets] == ["b2"]
    assert res.drafts[-1].violations == []


def test_max_pages_trims_bullets(tmp_path):
    res = run_pipeline(make_input(max_pages=1), make_deps())
    assert res.drafts[-1].pages.count == 1


def test_graph_has_the_v1_nodes():
    g = build_graph(Ctx(make_input(), make_deps()), None)
    names = set(g.get_graph().nodes)
    assert set(STEPS) <= names and "ask_user" in names


# --- interrupt + resume -------------------------------------------------------
def test_ask_user_interrupts_and_resumes_from_the_checkpoint(tmp_path):
    path = str(tmp_path / "ck.db")
    llm = FakeLLM(ask=["Kubernetes"])
    agent = GraphTailorAgent(make_deps(llm), path=path)
    ev = []
    first = agent.run(make_input(events=ev), lambda: False)
    assert [q.skill for q in first.questions] == ["Kubernetes"] and not first.drafts
    assert [s for s, _ in ev] == ["load_context", "rank_items", "plan"]

    # A fresh agent object (a new process) finds the paused graph on disk.
    saver = open_checkpointer(path)
    cfg = {"configurable": {"thread_id": "run1"}}
    assert saver.get_tuple(cfg) is not None
    agent2 = GraphTailorAgent(make_deps(FakeLLM(ask=["Kubernetes"])), path=path)
    ev2 = []
    answers = [("Kubernetes", "yes", "two years on EKS")]
    second = agent2.run(make_input(events=ev2, answers=answers), lambda: False)
    assert second.questions == [] and len(second.drafts) == 1
    assert [s for s, _ in ev2][:3] == ["load_context", "rank_items", "plan"]
    assert saver.get_tuple(cfg) is None  # finished: checkpoint cleaned up

    # the same inputs through the plain pipeline give the same drafts
    ref = run_pipeline(
        make_input(answers=answers), make_deps(FakeLLM(ask=["Kubernetes"]))
    )
    assert dump(ref)[0] == dump(second)[0]


def test_a_new_run_with_a_finished_thread_starts_fresh(tmp_path):
    agent = GraphTailorAgent(make_deps(), path=str(tmp_path / "ck.db"))
    a = agent.run(make_input(), lambda: False)
    b = agent.run(make_input(), lambda: False)
    assert dump(a)[0] == dump(b)[0] and len(b.drafts) == 1


def test_cancel_stops_at_a_step_boundary(tmp_path):
    calls = iter([False, False, True])
    agent = GraphTailorAgent(make_deps(), path=str(tmp_path / "ck.db"))
    res = agent.run(make_input(), lambda: next(calls, True))
    assert res.drafts == [] and res.questions == []


def test_llm_unreachable_propagates_as_transient(tmp_path):
    agent = GraphTailorAgent(
        make_deps(FakeLLM(error=TransientError("down"))), path=str(tmp_path / "c.db")
    )
    with pytest.raises(TransientError):
        agent.run(make_input(), lambda: False)


# --- plugged into the real `tailor` task ----------------------------------------
def test_tailor_task_with_graph_agent_emits_step_events(db_session, tmp_path):
    user = make_user(db_session)
    run = run_ready(db_session, tmp_path, user, status="queued")
    agent = GraphTailorAgent(make_deps(), path=str(tmp_path / "ck.db"))
    run_tasks.tailor(make_ctx(db_session, tmp_path, agent=agent), user.id, run.id)
    db_session.refresh(run)
    assert run.status == "in_review" and run.iteration == 1
    assert run.prompt_version and run.models == {"tailor": "fake-llm"}
    steps = [
        e.payload["step"]
        for e in db_session.scalars(select(RunEvent).order_by(RunEvent.seq))
        if e.type == "step"
    ]
    assert steps == list(STEPS)


def test_tailor_task_asks_then_resumes(db_session, tmp_path):
    user = make_user(db_session)
    run = run_ready(db_session, tmp_path, user, status="queued")
    agent = GraphTailorAgent(
        make_deps(FakeLLM(ask=["Kubernetes"])), path=str(tmp_path / "ck.db")
    )
    run_tasks.tailor(make_ctx(db_session, tmp_path, agent=agent), user.id, run.id)
    db_session.refresh(run)
    assert run.status == "waiting_for_user"
    assert run.pending_questions == [{"skill": "Kubernetes", "prompt": None}]
