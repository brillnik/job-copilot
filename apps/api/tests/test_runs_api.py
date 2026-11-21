import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.core import signing
from app.core.config import settings
from app.core.security import token_claims
from app.main import app
from app.models.job import AgentRun, Job, RunQuota, UserAnswer
from app.models.run import Approval, Draft
from app.models.tracker import TrackerCard
from app.repositories.manager import RepositoryManager
from app.services.tracker import TrackerService
from tests.jobs_helpers import approve_profile, make_user
from tests.runs_helpers import PROFILE, run_ready

client = TestClient(app)


@pytest.fixture(autouse=True)
def auth():
    app.dependency_overrides[token_claims] = lambda: {"sub": "auth0|A"}


@pytest.fixture
def user(db_session):
    return make_user(db_session)


def as_user(sub):
    app.dependency_overrides[token_claims] = lambda: {"sub": sub}


# --- reading -----------------------------------------------------------------
def test_list_filters_and_paginates(db_session, tmp_path, user):
    a = run_ready(db_session, tmp_path, user)
    run_ready(db_session, tmp_path, user, status="queued")
    run_ready(db_session, tmp_path, user, status="in_review")
    r = client.get("/runs", params={"status": "in_review"})
    assert r.status_code == 200 and len(r.json()["items"]) == 2
    item = next(i for i in r.json()["items"] if i["id"] == a.id)
    assert item["company"] == "Globex Corp" and item["title"] == "Backend Engineer"
    assert item["score"] == 80 and item["coverage"] == "1/2" and item["pages"] == 1
    assert item["flagged"] is False
    assert item["top_changes"] == [
        "Reworded: Built Kafka pipelines handling 2M events a day"
    ]
    assert len(client.get("/runs", params={"job_id": a.job_id}).json()["items"]) == 1
    page1 = client.get("/runs", params={"limit": 2}).json()
    assert len(page1["items"]) == 2 and page1["next_cursor"]
    page2 = client.get(
        "/runs", params={"limit": 2, "cursor": page1["next_cursor"]}
    ).json()
    assert len(page2["items"]) == 1 and page2["next_cursor"] is None
    assert client.get("/runs", params={"limit": 51}).status_code == 422
    assert client.get("/runs", params={"status": "bogus"}).status_code == 422


def test_detail_has_per_bullet_diff_and_history(db_session, tmp_path, user):
    run = run_ready(db_session, tmp_path, user)
    r = client.get(f"/runs/{run.id}")
    assert r.status_code == 200 and r.headers["etag"] == '"1"'
    body = r.json()
    assert body["profile_version"] == 1 and body["iterations"] == [
        {"iteration": 1, "outcome": "first pass"}
    ]
    b1 = body["bullets"][0]
    assert b1["source_text"] == "Built Kafka pipelines processing 2M events a day"
    assert b1["reverted"] is False
    assert [s["op"] for s in b1["diff"]] == ["same", "del", "add", "same"]
    assert body["bullets"][1]["diff"] == [
        {"op": "same", "text": "Led the migration of Postgres to Aurora"}
    ]
    assert body["coverage"]["pct"] == 0.5 and body["pages"]["count"] == 1
    assert body["has_pdf"] is True and body["skills_order"] == ["Python", "Postgres"]


# --- answer ------------------------------------------------------------------
@pytest.mark.parametrize("status", ["queued", "running", "in_review", "approved"])
def test_answer_conflicts_unless_waiting(db_session, tmp_path, user, queue, status):
    run = run_ready(db_session, tmp_path, user, status=status)
    r = client.post(
        f"/runs/{run.id}/answer",
        json={"answers": [{"skill": "Kubernetes", "answer": "no"}]},
    )
    assert r.status_code == 409 and r.json()["code"] == "invalid_state"
    assert "tailor" not in queue.names()


def test_answer_resumes_run_and_upserts(db_session, tmp_path, user, queue):
    run = run_ready(db_session, tmp_path, user, status="waiting_for_user")
    body = {
        "answers": [
            {"skill": "kubernetes", "answer": "yes", "detail": "ran EKS clusters"}
        ]
    }
    r = client.post(f"/runs/{run.id}/answer", json=body)
    assert r.status_code == 202 and r.json() == {"run_id": run.id, "status": "queued"}
    assert queue.calls[-1] == (
        "tailor", {"user_id": str(user.id), "run_id": run.id, "resume": True},
    )  # fmt: skip
    db_session.refresh(run)
    assert run.status == "queued" and run.pending_questions == []
    rows = db_session.scalars(select(UserAnswer)).all()
    assert [(a.skill, a.answer, a.detail) for a in rows] == [
        ("kubernetes", "yes", "ran EKS clusters")
    ]
    # the confirmed fact reaches the profile draft through the profile service
    draft = RepositoryManager(db_session).profiles.get_draft(user.id)
    assert "kubernetes" in {s.lower() for s in draft.data["skills"]}
    # answering again later upserts, never duplicates
    run2 = run_ready(db_session, tmp_path, user, status="waiting_for_user")
    client.post(
        f"/runs/{run2.id}/answer",
        json={"answers": [{"skill": "Kubernetes", "answer": "no"}]},
    )
    rows = db_session.scalars(select(UserAnswer)).all()
    assert len(rows) == 1 and rows[0].answer == "no" and rows[0].detail is None


def test_answer_for_a_skill_that_was_not_asked_is_rejected(db_session, tmp_path, user):
    run = run_ready(db_session, tmp_path, user, status="waiting_for_user")
    r = client.post(
        f"/runs/{run.id}/answer",
        json={"answers": [{"skill": "Haskell", "answer": "yes"}]},
    )
    assert r.status_code == 422 and r.json()["details"] == {"skills": ["Haskell"]}
    db_session.refresh(run)
    assert run.status == "waiting_for_user"


# --- edit draft --------------------------------------------------------------
def edit(run, etag=None, **body):
    headers = {"If-Match": etag} if etag else {}
    return client.put(f"/runs/{run.id}/draft", json=body, headers=headers)


def test_edit_applies_clean_changes_and_rerenders(db_session, tmp_path, user, queue):
    run = run_ready(db_session, tmp_path, user)
    r = edit(
        run,
        '"1"',
        bullets=[{"source_id": "b2", "text": "Led Postgres migration to Aurora"}],
    )
    assert r.status_code == 200, r.text
    out = r.json()
    assert out["applied"] == ["bullet:b2"] and out["violations"] == []
    assert (
        out["run"]["bullets"][1]["tailored_text"] == "Led Postgres migration to Aurora"
    )
    assert (
        out["run"]["edited"] is True and out["run"]["has_pdf"] is False
    )  # stale PDF dropped
    assert r.headers["etag"] == '"2"'
    assert queue.calls[-1][0] == "render_pdf"
    draft = db_session.scalar(select(Draft))
    assert draft.rev == 2 and draft.pdf_key is None


def test_stale_edit_is_409_and_changes_nothing(db_session, tmp_path, user):
    run = run_ready(db_session, tmp_path, user)
    assert edit(run, '"1"', summary="Backend engineer").status_code == 200
    r = edit(run, '"1"', summary="Engineer who builds Python systems")
    assert r.status_code == 409 and r.json()["code"] == "stale_write"
    assert r.json()["details"] == {"rev": 2}
    assert (
        edit(run, '"2"', summary="Engineer who builds Python systems").status_code
        == 200
    )
    # nothing to apply, but still stale: also refused
    assert edit(run, '"1"', summary="x" * 5 + " Python").status_code == 409


def test_unsupported_skill_is_blocked_by_the_fact_check(
    db_session, tmp_path, user, queue
):
    run = run_ready(db_session, tmp_path, user)
    r = edit(run, summary="Backend engineer experienced with Kubernetes and Python")
    assert r.status_code == 200
    out = r.json()
    assert out["applied"] == []  # nothing invented gets through
    assert [(v["code"], v["term"], v["blocked"]) for v in out["violations"]] == [
        ("unsupported_skill", "kubernetes", True)
    ]
    assert (
        out["run"]["summary"] == "Backend engineer with Python and Postgres experience"
    )
    assert out["run"]["draft_rev"] == 1 and "render_pdf" not in queue.names()


def test_invented_numbers_and_foreign_bullets_and_skills_are_blocked(
    db_session, tmp_path, user
):
    run = run_ready(db_session, tmp_path, user)
    out = edit(
        run,
        bullets=[
            {
                "source_id": "b1",
                "text": "Built Kafka pipelines processing 50M events a day",
            },
            {"source_id": "zzz", "text": "Made something up"},
        ],
        skills_order=["Python", "Go"],
    ).json()
    assert out["applied"] == []
    assert {(v["code"], v["term"] or v["source_id"]) for v in out["violations"]} == {
        ("invented_number", "50"),
        ("unknown_source", "zzz"),
        ("unsupported_skill", "Go"),
    }


def test_confirmed_answers_make_a_skill_claimable(db_session, tmp_path, user):
    run = run_ready(db_session, tmp_path, user)
    db_session.add(
        UserAnswer(user_id=user.id, skill="kubernetes", answer="yes", detail="EKS")
    )
    db_session.commit()
    out = edit(run, summary="Backend engineer experienced with Kubernetes").json()
    assert out["applied"] == ["summary"] and out["violations"] == []


@pytest.mark.parametrize("status", ["queued", "approved", "rejected"])
def test_edit_only_in_review(db_session, tmp_path, user, status):
    run = run_ready(db_session, tmp_path, user, status=status)
    assert edit(run, summary="Python").status_code == 409
    assert edit(run).status_code == 422  # empty body


# --- approve -----------------------------------------------------------------
def test_approve_writes_everything(db_session, tmp_path, user):
    run = run_ready(db_session, tmp_path, user)
    r = client.post(f"/runs/{run.id}/approve")
    assert r.status_code == 200, r.text
    ap = db_session.scalar(select(Approval))
    assert r.json() == {
        "approval_id": ap.id,
        "file_name": "Ada-Lovelace_globex-corp.pdf",
    }
    assert ap.decision == "approved" and ap.edits_applied is False
    assert ap.final["bullets"][0]["source_id"] == "b1"
    key = f"users/{user.id.hex}/resumes/{run.id}.pdf"
    assert ap.pdf_key == key and (tmp_path / key).read_bytes().startswith(b"%PDF")
    db_session.refresh(run)
    assert run.status == "approved"
    assert db_session.get(Job, run.job_id).status == "approved"
    (card,) = db_session.scalars(select(TrackerCard)).all()
    assert (card.job_id, card.column) == (run.job_id, "approved")


def test_approve_is_idempotent(db_session, tmp_path, user, queue):
    run = run_ready(db_session, tmp_path, user)
    first = client.post(f"/runs/{run.id}/approve").json()
    second = client.post(f"/runs/{run.id}/approve")
    assert second.status_code == 200 and second.json() == first
    assert len(db_session.scalars(select(Approval)).all()) == 1
    assert len(db_session.scalars(select(TrackerCard)).all()) == 1


@pytest.mark.parametrize(
    "status", ["queued", "running", "waiting_for_user", "cancelled", "rejected"]
)
def test_approve_only_from_in_review(db_session, tmp_path, user, status):
    run = run_ready(db_session, tmp_path, user, status=status)
    r = client.post(f"/runs/{run.id}/approve")
    assert r.status_code == 409 and r.json()["code"] == "invalid_state"
    assert db_session.scalars(select(Approval)).all() == []


def test_approve_waits_for_the_pdf_after_an_edit(db_session, tmp_path, user):
    run = run_ready(db_session, tmp_path, user)
    edit(run, summary="Backend engineer")
    r = client.post(f"/runs/{run.id}/approve")
    assert r.status_code == 409 and r.json()["code"] == "pdf_not_ready"


def test_approve_includes_edits(db_session, tmp_path, user):
    from app.tasks import runs as run_tasks
    from tests.jobs_helpers import make_ctx

    run = run_ready(db_session, tmp_path, user)
    edit(run, summary="Backend engineer, Python")
    run_tasks.render_pdf(make_ctx(db_session, tmp_path), user.id, run.id)
    assert client.post(f"/runs/{run.id}/approve").status_code == 200
    ap = db_session.scalar(select(Approval))
    assert (
        ap.edits_applied is True and ap.final["summary"] == "Backend engineer, Python"
    )


def test_failed_approve_leaves_nothing_half_written(
    db_session, tmp_path, user, monkeypatch
):
    run = run_ready(db_session, tmp_path, user)

    def boom(self, user_id, job_id):
        raise RuntimeError("db went away")

    with monkeypatch.context() as m:
        m.setattr(TrackerService, "upsert_for_approval", boom)
        r = TestClient(app, raise_server_exceptions=False).post(
            f"/runs/{run.id}/approve"
        )
    assert r.status_code == 500
    db_session.rollback()
    assert db_session.scalars(select(Approval)).all() == []
    assert db_session.scalars(select(TrackerCard)).all() == []
    db_session.refresh(run)
    assert run.status == "in_review"
    assert db_session.get(Job, run.job_id).status == "in_review"
    assert not (tmp_path / f"users/{user.id.hex}/resumes/{run.id}.pdf").exists()
    # and it still works once the fault is gone
    assert client.post(f"/runs/{run.id}/approve").status_code == 200


# --- reject / regenerate / cancel -------------------------------------------
def test_reject_stores_reasons(db_session, tmp_path, user):
    run = run_ready(db_session, tmp_path, user)
    r = client.post(
        f"/runs/{run.id}/reject",
        json={"reasons": ["tone", "too_generic", "tone"], "note": "stiff"},
    )
    assert r.status_code == 200 and r.json() == {"run_id": run.id, "status": "rejected"}
    db_session.refresh(run)
    assert run.reject_reasons == ["tone", "too_generic"] and run.reject_note == "stiff"
    assert db_session.get(Job, run.job_id).status == "rejected"
    ap = db_session.scalar(select(Approval))
    assert ap.decision == "rejected" and ap.reasons == ["tone", "too_generic"]
    assert client.post(f"/runs/{run.id}/reject", json={}).status_code == 409
    assert client.post(f"/runs/{run.id}/approve").status_code == 409


def test_reject_validates_reasons(db_session, tmp_path, user):
    run = run_ready(db_session, tmp_path, user)
    assert (
        client.post(f"/runs/{run.id}/reject", json={"reasons": ["rude"]}).status_code
        == 422
    )
    db_session.refresh(run)
    assert run.status == "in_review"


def test_regenerate_pins_current_profile_and_carries_guidance(
    db_session, tmp_path, user, queue
):
    run = run_ready(db_session, tmp_path, user)
    client.post(
        f"/runs/{run.id}/reject",
        json={"reasons": ["wrong_emphasis"], "note": "lead with Kafka"},
    )
    newer = PROFILE.model_copy(update={"skills": ["Python", "Postgres", "Go"]})
    approve_profile(db_session, user, newer)  # profile version 2
    r = client.post(f"/runs/{run.id}/regenerate", json={"max_pages": 2})
    assert r.status_code == 202, r.text
    new = db_session.get(AgentRun, r.json()["run_id"])
    assert new.id != run.id and new.job_id == run.job_id
    assert (new.status, new.profile_version, new.max_pages) == ("queued", 2, 2)
    assert new.guidance == {
        "from_run": run.id, "reasons": ["wrong_emphasis"], "note": "lead with Kafka",
    }  # fmt: skip
    assert db_session.get(Job, run.job_id).max_pages_override == 2
    assert db_session.get(Job, run.job_id).status == "tailoring"
    assert queue.calls[-1] == ("tailor", {"user_id": str(user.id), "run_id": new.id})


def test_regenerate_can_skip_guidance(db_session, tmp_path, user):
    run = run_ready(db_session, tmp_path, user)
    client.post(f"/runs/{run.id}/reject", json={"reasons": ["tone"]})
    r = client.post(
        f"/runs/{run.id}/regenerate", json={"guidance_from_rejection": False}
    )
    new = db_session.get(AgentRun, r.json()["run_id"])
    assert new.guidance is None and new.max_pages is None


def test_regenerate_from_review_supersedes_the_old_run(db_session, tmp_path, user):
    run = run_ready(db_session, tmp_path, user)
    r = client.post(f"/runs/{run.id}/regenerate")
    assert r.status_code == 202
    db_session.refresh(run)
    assert (run.status, run.status_reason) == ("rejected", "regenerated")
    assert (
        db_session.get(Job, run.job_id).status == "tailoring"
    )  # the new run owns the job
    assert client.post(f"/runs/{run.id}/approve").status_code == 409


def test_regenerate_respects_the_daily_cap(db_session, tmp_path, user, monkeypatch):
    run = run_ready(db_session, tmp_path, user, status="needs_attention")
    monkeypatch.setattr(
        settings, "daily_run_cap", 1
    )  # needs_attention gave its slot back
    assert client.post(f"/runs/{run.id}/regenerate").status_code == 202
    other = run_ready(db_session, tmp_path, user, status="in_review")
    r = client.post(f"/runs/{other.id}/regenerate")
    assert r.status_code == 429 and r.json()["code"] == "daily_cap"
    db_session.refresh(other)
    assert other.status == "in_review"  # a refused regenerate changes nothing


@pytest.mark.parametrize(
    "status", ["queued", "running", "waiting_for_user", "approved", "cancelled"]
)
def test_regenerate_state_rules(db_session, tmp_path, user, status):
    run = run_ready(db_session, tmp_path, user, status=status)
    assert client.post(f"/runs/{run.id}/regenerate").status_code == 409


def used(db, user):
    return db.scalar(select(RunQuota.used).where(RunQuota.user_id == user.id))


@pytest.mark.parametrize("status", ["queued", "running", "waiting_for_user"])
def test_cancel_stops_counting_against_the_cap(db_session, tmp_path, user, status):
    run = run_ready(db_session, tmp_path, user, status=status)
    assert used(db_session, user) == 1
    r = client.post(f"/runs/{run.id}/cancel")
    assert r.status_code == 200 and r.json()["status"] == "cancelled"
    db_session.expire_all()
    assert used(db_session, user) == 0
    assert db_session.get(Job, run.job_id).status == "new"
    assert client.post(f"/runs/{run.id}/cancel").status_code == 409  # no double refund
    assert used(db_session, user) == 0


@pytest.mark.parametrize(
    "status", ["in_review", "approved", "rejected", "needs_attention"]
)
def test_cancel_only_while_active(db_session, tmp_path, user, status):
    run = run_ready(db_session, tmp_path, user, status=status)
    assert client.post(f"/runs/{run.id}/cancel").status_code == 409


def test_needs_attention_is_not_counted(db_session, tmp_path, user):
    run_ready(db_session, tmp_path, user, status="needs_attention")
    assert used(db_session, user) == 0
    run_ready(db_session, tmp_path, user, status="in_review")
    assert used(db_session, user) == 1


# --- pdf ---------------------------------------------------------------------
def test_pdf_redirects_to_a_short_lived_signed_url(
    db_session, tmp_path, user, monkeypatch
):
    run = run_ready(db_session, tmp_path, user)
    r = client.get(f"/runs/{run.id}/pdf", follow_redirects=False)
    assert r.status_code == 302 and r.headers["location"].startswith("/files/")
    url = r.headers["location"]
    got = client.get(url)
    assert got.status_code == 200 and got.content.startswith(b"%PDF")
    assert got.headers["content-type"] == "application/pdf"
    claims = signing.verify(url.removeprefix("/files/"))
    assert claims["exp"] - signing.now() <= 300
    now = signing.now()
    monkeypatch.setattr(signing, "now", lambda: now + 301)
    expired = client.get(url)
    assert expired.status_code == 403 and expired.json()["code"] == "invalid_link"
    assert (
        client.get("/files/" + url.removeprefix("/files/")[:-3] + "abc").status_code
        == 403
    )


def test_pdf_approved_needs_an_approval(db_session, tmp_path, user):
    run = run_ready(db_session, tmp_path, user)
    assert (
        client.get(
            f"/runs/{run.id}/pdf?draft=approved", follow_redirects=False
        ).status_code
        == 404
    )
    client.post(f"/runs/{run.id}/approve")
    r = client.get(f"/runs/{run.id}/pdf?draft=approved", follow_redirects=False)
    assert r.status_code == 302
    assert (
        'filename="Ada-Lovelace_globex-corp.pdf"'
        in client.get(r.headers["location"]).headers["content-disposition"]
    )
    assert client.get(f"/runs/{run.id}/pdf?draft=nope").status_code == 422


# --- isolation ---------------------------------------------------------------
def test_other_users_run_is_404_everywhere(db_session, tmp_path, user):
    run = run_ready(db_session, tmp_path, user)
    waiting = run_ready(db_session, tmp_path, user, status="waiting_for_user")
    as_user("auth0|B")
    make_user(db_session, "auth0|B")
    calls = [
        ("get", f"/runs/{run.id}", None),
        ("get", f"/runs/{run.id}/events", None),
        (
            "post",
            f"/runs/{waiting.id}/answer",
            {"answers": [{"skill": "Kubernetes", "answer": "no"}]},
        ),
        ("put", f"/runs/{run.id}/draft", {"summary": "Python"}),
        ("post", f"/runs/{run.id}/approve", None),
        ("post", f"/runs/{run.id}/reject", {}),
        ("post", f"/runs/{run.id}/regenerate", None),
        ("post", f"/runs/{waiting.id}/cancel", None),
        ("get", f"/runs/{run.id}/pdf", None),
        ("get", f"/runs/{run.id}/pdf?draft=approved", None),
    ]
    for method, url, body in calls:
        r = getattr(client, method)(
            url, **({"json": body} if body is not None else {}), follow_redirects=False
        )
        assert r.status_code == 404, (method, url, r.status_code)
        assert r.json()["code"] == "not_found"
    assert client.get("/runs").json()["items"] == []
    assert client.get("/runs", params={"job_id": run.job_id}).json()["items"] == []
    db_session.refresh(run)
    assert (
        run.status == "in_review" and db_session.scalars(select(Approval)).all() == []
    )
