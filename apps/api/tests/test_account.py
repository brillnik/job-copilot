import io
import time
import zipfile
from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.core import signing
from app.core.config import settings
from app.core.security import token_claims
from app.db.base import Base
from app.main import app
from app.models.account import ConsentLog, DeletionAudit, Export
from app.models.job import AgentRun, Event
from app.models.user import User
from app.services import crypto
from app.tasks import account as acct
from app.tasks.queue import RecordingQueue
from tests.account_helpers import data_rows, seed
from tests.jobs_helpers import make_ctx, make_user

client = TestClient(app)


def claims_for(sub, iat=None, **extra):
    app.dependency_overrides[token_claims] = lambda: {
        "sub": sub,
        "iat": int(time.time()) - 5 if iat is None else iat,
        **extra,
    }


@pytest.fixture(autouse=True)
def auth():
    claims_for("auth0|A")


class RecordingMailer:
    def __init__(self):
        self.sent = []

    def send(self, user_id, template, **params):
        self.sent.append((user_id, template, params))


# --- /me and consent ---------------------------------------------------------
def test_me(db_session):
    user = make_user(db_session, "google-oauth2|123")
    user.name = "Ada"
    db_session.commit()
    claims_for("google-oauth2|123")
    body = client.get("/me").json()
    assert body["id"] == str(user.id) and body["email"] == "google-oauth2|123@x.co"
    assert body["auth_providers"] == ["google-oauth2"] and body["consent"] is None
    assert body["plan"] == "free" and body["created_at"]


def test_consent_is_an_append_only_log(db_session):
    user = make_user(db_session)
    first = client.post("/me/consent", json={"policy_version": "2026-01"})
    assert first.status_code == 201 and first.json()["policy_version"] == "2026-01"
    second = client.post("/me/consent", json={"policy_version": "2026-06"})
    rows = db_session.scalars(select(ConsentLog).order_by(ConsentLog.created_at)).all()
    assert [r.policy_version for r in rows] == [
        "2026-01",
        "2026-06",
    ]  # appended, not replaced
    assert all(r.user_id == user.id for r in rows)
    me = client.get("/me").json()["consent"]
    assert me["policy_version"] == "2026-06"
    assert me["at"].rstrip("Z") == second.json()["at"].rstrip("Z")
    assert client.post("/me/consent", json={"policy_version": ""}).status_code == 422
    assert (
        client.post("/me/consent", json={"policy_version": "1", "x": 1}).status_code
        == 422
    )
    assert not hasattr(client.app.routes, "put_consent")
    assert client.put("/me/consent", json={"policy_version": "1"}).status_code == 405


# --- logout everywhere -------------------------------------------------------
def test_logout_all_revokes_every_earlier_token(db_session):
    make_user(db_session)
    old = int(time.time()) - 600
    claims_for("auth0|A", iat=old)
    assert client.get("/me").status_code == 200
    assert client.post("/auth/logout-all").status_code == 204
    r = client.get("/me")
    assert r.status_code == 401 and r.json()["code"] == "session_revoked"
    claims_for("auth0|A", iat=old + 30)  # another still-valid token from before
    assert client.get("/me").status_code == 401
    claims_for("auth0|A", iat=int(time.time()) + 5)  # signed in again afterwards
    assert client.get("/me").status_code == 200


def test_logout_all_only_touches_that_user(db_session):
    make_user(db_session)
    make_user(db_session, "auth0|B")
    client.post("/auth/logout-all")
    claims_for("auth0|B", iat=int(time.time()) - 600)
    assert client.get("/me").status_code == 200


# --- export ------------------------------------------------------------------
def run_export(db, tmp_path, user, mailer=None):
    ctx = make_ctx(db, tmp_path, mailer=mailer or RecordingMailer())
    export_id = client.post("/me/export").json()["export_id"]
    acct.export_user(ctx, user.id, export_id)
    return export_id, ctx


def open_export(tmp_path, user, export_id):
    raw = (tmp_path / acct.export_key(user.id, export_id)).read_bytes()
    return raw, zipfile.ZipFile(io.BytesIO(crypto.decrypt(raw)))


def test_export_request_is_deduplicated_while_pending(db_session, queue):
    make_user(db_session)
    first = client.post("/me/export")
    assert first.status_code == 202
    assert client.post("/me/export").json() == first.json()
    assert queue.names() == ["export_user"]
    status = client.get(f"/me/export/{first.json()['export_id']}").json()
    assert status["status"] == "queued" and status["download_url"] is None


def test_export_contains_every_data_type_and_only_this_users(db_session, tmp_path):
    a, *_ = seed(db_session, tmp_path, "auth0|A", "ALPHA")
    b, *_ = seed(db_session, tmp_path, "auth0|B", "BRAVO")
    claims_for("auth0|A")
    mailer = RecordingMailer()
    export_id, _ = run_export(db_session, tmp_path, a, mailer)

    raw, z = open_export(tmp_path, a, export_id)
    assert not raw.startswith(b"PK") and b"ALPHA" not in raw  # encrypted at rest
    names = set(z.namelist())
    assert {
        "profiles.json", "jobs.json", "jd_extractions.json", "runs.json", "run_events.json",
        "drafts.json", "approvals.json", "tracker.json", "answers.json", "consent.json",
        "settings.json",
    } <= names  # fmt: skip
    assert any(
        n.startswith("files/resumes/") and n.endswith("cv-ALPHA.pdf") for n in names
    )
    assert any(n.startswith("files/uploads/") for n in names)
    assert any(n.startswith("files/drafts/") for n in names)
    assert "files/approved/Ada-ALPHA_co-alpha.pdf" in names
    everything = b"".join(z.read(n) for n in names)
    for marker in (b"ALPHA", b"Built Kafka", b"skill-ALPHA", b"posting ALPHA"):
        assert marker in everything
    assert b"BRAVO" not in everything and str(b.id).encode() not in everything
    assert z.read("files/approved/Ada-ALPHA_co-alpha.pdf").startswith(b"%PDF")
    # every row in every JSON belongs to A
    import json

    for name in names:
        if name.endswith(".json") and name != "settings.json":
            for row in json.loads(z.read(name)) if name != "missing_files.json" else []:
                assert row.get("user_id", str(a.id)) == str(a.id)

    # notified by event and email
    ev = db_session.scalars(select(Event).where(Event.type == "export_ready")).all()
    assert [e.user_id for e in ev] == [a.id] and ev[0].payload == {
        "export_id": export_id
    }
    assert mailer.sent == [(str(a.id), "export_ready", {"export_id": export_id})]


def test_export_link_is_signed_and_expires_after_24_hours(
    db_session, tmp_path, monkeypatch
):
    a, *_ = seed(db_session, tmp_path, "auth0|A", "ALPHA")
    claims_for("auth0|A")
    export_id, _ = run_export(db_session, tmp_path, a)
    body = client.get(f"/me/export/{export_id}").json()
    assert body["status"] == "ready" and body["expires_at"]
    url = body["download_url"]
    got = client.get(url)
    assert got.status_code == 200 and got.headers["content-type"] == "application/zip"
    assert (
        zipfile.ZipFile(io.BytesIO(got.content)).testzip() is None
    )  # served decrypted
    claims = signing.verify(url.removeprefix("/files/"))
    assert abs(claims["exp"] - signing.now() - 24 * 3600) < 5
    now = signing.now()
    monkeypatch.setattr(signing, "now", lambda: now + 24 * 3600 + 5)
    assert client.get(url).status_code == 403
    assert client.get(f"/me/export/{export_id}").json()[
        "download_url"
    ]  # a fresh link is available


def test_exports_expire_after_seven_days(db_session, tmp_path):
    a, *_ = seed(db_session, tmp_path, "auth0|A", "ALPHA")
    claims_for("auth0|A")
    export_id, ctx = run_export(db_session, tmp_path, a)
    export = db_session.get(Export, export_id)
    assert (export.expires_at - export.ready_at).days == 7 or (
        export.expires_at.replace(tzinfo=UTC) - export.ready_at.replace(tzinfo=UTC)
    ) == timedelta(days=settings.export_ttl_days)
    assert acct.expire_exports(ctx) == 0
    export.expires_at = datetime.now(UTC) - timedelta(seconds=1)
    db_session.commit()
    body = client.get(f"/me/export/{export_id}").json()
    assert body["status"] == "expired" and body["download_url"] is None
    assert acct.expire_exports(ctx) == 1
    assert not (tmp_path / acct.export_key(a.id, export_id)).exists()
    assert db_session.get(Export, export_id).status == "expired"


def test_a_failed_export_is_reported(db_session, tmp_path, monkeypatch):
    a = make_user(db_session)
    ctx = make_ctx(db_session, tmp_path)
    export_id = client.post("/me/export").json()["export_id"]
    monkeypatch.setattr(
        acct, "build_export", lambda *a: (_ for _ in ()).throw(OSError("disk"))
    )
    acct.export_user(ctx, a.id, export_id)
    assert client.get(f"/me/export/{export_id}").json()["status"] == "failed"
    assert client.post("/me/export").json()["export_id"] != export_id  # can retry


# --- delete ------------------------------------------------------------------
def test_delete_needs_the_confirmation_word(db_session):
    make_user(db_session)
    for body in (
        {},
        {"confirm": "delete"},
        {"confirm": "yes"},
        {"confirm": "DELETE", "x": 1},
    ):
        assert client.request("DELETE", "/me", json=body).status_code == 422
    assert db_session.scalar(select(User.status)) == "active"


def test_delete_needs_a_recent_sign_in(db_session, queue):
    make_user(db_session)
    claims_for("auth0|A", iat=int(time.time()) - 3600)
    r = client.request("DELETE", "/me", json={"confirm": "DELETE"})
    assert r.status_code == 401 and r.json()["code"] == "reauth_required"
    assert db_session.scalar(select(User.status)) == "active" and queue.calls == []
    # auth_time (when the user last typed their password) beats a fresh refresh token
    claims_for("auth0|A", iat=int(time.time()), auth_time=int(time.time()) - 3600)
    assert (
        client.request("DELETE", "/me", json={"confirm": "DELETE"}).status_code == 401
    )
    claims_for("auth0|A", iat=int(time.time()) - 3600, auth_time=int(time.time()) - 60)
    assert (
        client.request("DELETE", "/me", json={"confirm": "DELETE"}).status_code == 202
    )


def test_delete_acts_immediately(db_session, tmp_path, queue):
    a, run, waiting = seed(db_session, tmp_path, "auth0|A", "ALPHA")
    claims_for("auth0|A")
    r = client.request("DELETE", "/me", json={"confirm": "DELETE"})
    assert r.status_code == 202 and r.json() == {"status": "deleting"}
    db_session.refresh(a)
    assert a.status == "deleting" and a.sessions_valid_after is not None
    db_session.refresh(waiting)
    assert waiting.status == "cancelled"
    assert (
        db_session.get(AgentRun, run.id).status == "approved"
    )  # finished runs are untouched
    assert queue.calls[-1] == ("delete_user", {"user_id": str(a.id)})
    # the account takes no further requests: the old token is dead...
    assert client.get("/me").status_code == 401
    # ...and so would a new one while the erasure is pending
    claims_for("auth0|A", iat=int(time.time()) + 10)
    r = client.get("/me")
    assert r.status_code == 403 and r.json()["code"] == "account_deleting"
    assert client.get("/jobs").status_code == 403


def test_delete_user_removes_everything_for_that_user_and_nothing_else(
    db_session, tmp_path
):
    a, *_ = seed(db_session, tmp_path, "auth0|A", "ALPHA")
    b, *_ = seed(db_session, tmp_path, "auth0|B", "BRAVO")
    claims_for("auth0|A")
    run_export(db_session, tmp_path, a)
    before_b = data_rows(db_session, b)
    files_b = sorted(
        p.relative_to(tmp_path).as_posix()
        for p in (tmp_path / "users" / b.id.hex).rglob("*")
        if p.is_file()
    )
    assert all(
        n > 0 for t, n in data_rows(db_session, a).items() if t != "deletion_audit"
    )  # fully seeded
    claims_for("auth0|A")
    client.request("DELETE", "/me", json={"confirm": "DELETE"})
    a_id, a_sub = a.id, a.auth0_sub

    acct.delete_user(make_ctx(db_session, tmp_path), a_id)

    db_session.expire_all()
    assert db_session.get(User, a_id) is None
    assert all(
        n == 0 for n in data_rows(db_session, a).values()
    )  # incl. bullet vectors
    assert (
        not (tmp_path / "users" / a_id.hex).exists()
        and not (tmp_path / a_id.hex).exists()
    )
    # B is untouched: rows, vectors and files
    assert data_rows(db_session, b) == before_b and before_b["profile_bullets"] > 0
    assert (
        sorted(
            p.relative_to(tmp_path).as_posix()
            for p in (tmp_path / "users" / b.id.hex).rglob("*")
            if p.is_file()
        )
        == files_b
    )
    assert (tmp_path / b.id.hex / "resume-BRAVO.pdf").exists()
    assert db_session.get(User, b.id).name == "name-BRAVO"
    # only a minimal audit record remains
    (audit,) = db_session.scalars(select(DeletionAudit)).all()
    assert len(audit.user_id_hash) == 64 and audit.deleted_at
    dumped = repr([(c.name, getattr(audit, c.name)) for c in DeletionAudit.__table__.c])
    assert str(a_id) not in dumped and a_sub not in dumped and "ALPHA" not in dumped


def test_a_token_from_before_the_deletion_cannot_bring_the_account_back(
    db_session, tmp_path
):
    a, *_ = seed(db_session, tmp_path, "auth0|A", "ALPHA")
    claims_for("auth0|A")
    client.request("DELETE", "/me", json={"confirm": "DELETE"})
    acct.delete_user(make_ctx(db_session, tmp_path), a.id)
    claims_for("auth0|A", iat=int(time.time()) - 30)
    r = client.get("/me")
    assert r.status_code == 401 and r.json()["code"] == "account_deleted"
    assert db_session.scalar(select(User).where(User.auth0_sub == "auth0|A")) is None
    claims_for(
        "auth0|A", iat=int(time.time()) + 30
    )  # a genuine new sign-in starts fresh
    assert client.get("/me").status_code == 200
    assert db_session.scalar(select(User.id).where(User.auth0_sub == "auth0|A")) != a.id


def test_delete_user_refuses_an_account_not_marked_for_deletion(db_session, tmp_path):
    a, *_ = seed(db_session, tmp_path, "auth0|A", "ALPHA")
    before = data_rows(db_session, a)
    acct.delete_user(make_ctx(db_session, tmp_path), a.id)
    assert db_session.get(User, a.id) is not None and data_rows(db_session, a) == before


def test_delete_user_resumes_after_a_crash_midway(db_session, tmp_path, monkeypatch):
    a, *_ = seed(db_session, tmp_path, "auth0|A", "ALPHA")
    b, *_ = seed(db_session, tmp_path, "auth0|B", "BRAVO")
    before_b = data_rows(db_session, b)
    claims_for("auth0|A")
    client.request("DELETE", "/me", json={"confirm": "DELETE"})
    ctx = make_ctx(db_session, tmp_path)
    real = acct.purge_data

    def crash_after_half(session, user_id):
        half = acct.PURGE_ORDER[: len(acct.PURGE_ORDER) // 2]
        for model in half:
            session.execute(acct.delete(model).where(model.user_id == user_id))
            session.commit()
        raise RuntimeError("worker died")

    with monkeypatch.context() as m:
        m.setattr(acct, "purge_data", crash_after_half)
        with pytest.raises(RuntimeError):
            acct.delete_user(ctx, a.id)
    db_session.rollback()
    left = data_rows(db_session, a)
    assert (
        db_session.get(User, a.id).status == "deleting"
    )  # still marked: the job is unfinished
    assert (
        sum(left.values()) > 0 and left["run_events"] == 0
    )  # partial progress is real

    assert acct.resume_deletions(ctx) == 1  # the sweeper finishes it
    db_session.expire_all()
    assert db_session.get(User, a.id) is None
    assert all(n == 0 for n in data_rows(db_session, a).values())
    assert data_rows(db_session, b) == before_b
    assert acct.resume_deletions(ctx) == 0
    acct.delete_user(ctx, a.id)  # a third run changes nothing and does not fail
    assert len(db_session.scalars(select(DeletionAudit)).all()) == 1
    assert real is acct.purge_data


def test_every_table_with_user_data_is_purged():
    covered = {m.__table__.name for m in acct.PURGE_ORDER} | {"users", "deletion_audit"}
    holders = {t.name for t in Base.metadata.sorted_tables if "user_id" in t.c}
    assert holders <= covered, f"delete_user would leave data in: {holders - covered}"


def test_tasks_do_nothing_for_an_account_being_deleted(db_session, tmp_path):
    from app.tasks import runs as run_tasks
    from tests.runs_helpers import FakeAgent, run_ready

    a = make_user(db_session)
    run = run_ready(db_session, tmp_path, a, status="queued")
    a.status = "deleting"
    db_session.commit()
    agent = FakeAgent()
    run_tasks.tailor(
        make_ctx(db_session, tmp_path, agent=agent, queue=RecordingQueue()),
        a.id,
        run.id,
    )
    assert agent.inputs == []


# --- isolation ---------------------------------------------------------------
def test_other_users_export_is_404_and_never_downloadable(db_session, tmp_path):
    a, *_ = seed(db_session, tmp_path, "auth0|A", "ALPHA")
    claims_for("auth0|A")
    export_id, _ = run_export(db_session, tmp_path, a)
    make_user(db_session, "auth0|B")
    claims_for("auth0|B")
    r = client.get(f"/me/export/{export_id}")
    assert r.status_code == 404 and r.json()["code"] == "not_found"
    assert "download_url" not in r.text
    assert client.post("/me/export").json()["export_id"] != export_id
