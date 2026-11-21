import contextlib
import logging
import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.agent.examples import DbExampleSource, bucket, embed_jd, examples_enabled_for
from app.agent.llm import STYLE_RULE, Example, PlanOut, build_write_prompt
from app.agent.pipeline import run_pipeline
from app.ai.embeddings import HashingEmbedder
from app.core.config import settings
from app.core.security import token_claims
from app.main import app
from app.models.run import Approval
from app.schemas.job import JobDescription
from tests.agent_helpers import FakeLLM, make_deps, make_input
from tests.jobs_helpers import make_user
from tests.runs_helpers import JD, run_ready

EMB = HashingEmbedder()
JD_A = JobDescription(title="Backend Engineer", must_have=["Python", "Postgres"])
JD_FAR = JobDescription(title="Pastry chef", must_have=["croissants", "lamination"])


def approval(db, user, jd, final=None, run_id=None, model=EMB.name):
    a = Approval(
        user_id=user.id,
        run_id=run_id or uuid.uuid4().hex,
        job_id="j",
        decision="approved",
        final=final or {"summary": "S", "bullets": [{"source_id": "b1", "text": "T"}]},
        jd_embedding=embed_jd(EMB, jd),
        jd_embedding_model=model,
    )
    db.add(a)
    db.commit()
    return a


@pytest.fixture(autouse=True)
def _thresholds(monkeypatch):
    monkeypatch.setattr(settings, "tailor_examples_min_sim", 0.6)


def source(db):
    return DbExampleSource(lambda: contextlib.nullcontext(db), EMB)


def test_retrieval_filters_by_user_threshold_and_model(db_session):
    me, other = make_user(db_session, "auth0|A"), make_user(db_session, "auth0|B")
    near = approval(db_session, me, JD_A)
    approval(db_session, me, JD_FAR)  # dissimilar: below the threshold
    approval(db_session, me, JD_A, model="other-model")  # different vector space
    approval(db_session, other, JD_A)  # someone else's
    got = source(db_session).retrieve(str(me.id), JD_A)
    assert [e.approval_id for e in got] == [near.id]
    assert got[0].similarity >= 0.6
    assert source(db_session).retrieve(str(other.id), JD_FAR) == []


def test_retrieval_returns_at_most_three_best_first(db_session, monkeypatch):
    me = make_user(db_session)
    rows = [approval(db_session, me, JD_A) for _ in range(5)]
    got = source(db_session).retrieve(str(me.id), JD_A)
    assert len(got) == 3 and {e.approval_id for e in got} <= {r.id for r in rows}
    sims = [e.similarity for e in got]
    assert sims == sorted(sims, reverse=True)


def test_ids_only_are_logged(db_session, caplog):
    me = make_user(db_session)
    a = approval(db_session, me, JD_A, final={"summary": "SECRET-TEXT", "bullets": []})
    with caplog.at_level(logging.INFO):
        source(db_session).retrieve(str(me.id), JD_A)
    assert a.id in caplog.text and "SECRET-TEXT" not in caplog.text


def test_prompt_states_examples_are_style_only():
    ex = [Example("a1", None, "Style summary", ["Style bullet"], 0.9)]
    prompt = build_write_prompt(JD_A, [], PlanOut(), ["Python"], ex, [])
    assert STYLE_RULE in prompt and "style example 1" in prompt
    assert "facts may only come from this job's retrieved bullets" in prompt
    assert "style example" not in build_write_prompt(JD_A, [], PlanOut(), [], [], [])


# --- feature flag and A/B ------------------------------------------------------
def users_in_and_out(pct):
    ids = [uuid.UUID(int=i) for i in range(1, 400)]
    return [u for u in ids if bucket(u) < pct], [u for u in ids if bucket(u) >= pct]


def test_ab_assignment_is_deterministic_and_respects_percentage(monkeypatch):
    monkeypatch.setattr(settings, "tailor_examples_enabled", True)
    monkeypatch.setattr(settings, "tailor_examples_ab_pct", 50)
    inn, out = users_in_and_out(50)
    assert inn and out and 100 < len(inn) < 300
    assert all(examples_enabled_for(u) for u in inn[:20])
    assert not any(examples_enabled_for(u) for u in out[:20])
    assert examples_enabled_for(inn[0]) == examples_enabled_for(str(inn[0]))
    monkeypatch.setattr(settings, "tailor_examples_ab_pct", 0)
    assert not examples_enabled_for(inn[0])
    monkeypatch.setattr(settings, "tailor_examples_ab_pct", 100)
    assert examples_enabled_for(out[0])
    monkeypatch.setattr(settings, "tailor_examples_enabled", False)
    assert not examples_enabled_for(out[0])
    assert not examples_enabled_for(None)


class StubExamples:
    def __init__(self):
        self.calls = []

    def retrieve(self, user_id, jd):
        self.calls.append(user_id)
        return [Example("a1", None, "s", ["b"], 0.8)]


@pytest.mark.parametrize(
    "enabled,pct,expect", [(False, 100, 0), (True, 0, 0), (True, 100, 1)]
)
def test_agent_only_uses_examples_for_the_enabled_arm(
    monkeypatch, enabled, pct, expect
):
    monkeypatch.setattr(settings, "tailor_examples_enabled", enabled)
    monkeypatch.setattr(settings, "tailor_examples_ab_pct", pct)
    src, llm = StubExamples(), FakeLLM()
    uid = str(uuid.uuid4())
    run_pipeline(make_input(user_id=uid), make_deps(llm, examples=src))
    assert len(src.calls) == expect
    assert len(llm.write_calls[0][1]) == expect  # examples reach the write step


# --- approve stores the JD embedding ---------------------------------------------
client = TestClient(app)


def test_approve_stores_jd_embedding(db_session, tmp_path):
    app.dependency_overrides[token_claims] = lambda: {"sub": "auth0|A"}
    user = make_user(db_session)
    run = run_ready(db_session, tmp_path, user)
    assert client.post(f"/runs/{run.id}/approve").status_code == 200
    ap = db_session.scalar(select(Approval))
    assert ap.jd_embedding == embed_jd(EMB, JD) and ap.jd_embedding_model == EMB.name


def test_approve_survives_an_unavailable_embedder(db_session, tmp_path, monkeypatch):
    app.dependency_overrides[token_claims] = lambda: {"sub": "auth0|A"}

    def boom(*a, **k):
        raise RuntimeError("model missing")

    user = make_user(db_session)
    run = run_ready(db_session, tmp_path, user, render=True)
    monkeypatch.setattr(HashingEmbedder, "embed_documents", boom)
    assert client.post(f"/runs/{run.id}/approve").status_code == 200
    assert db_session.scalar(select(Approval)).jd_embedding is None
