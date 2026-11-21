from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient

from app.core.security import token_claims
from app.main import app
from app.models.discovery import ExtensionPairingCode, ExtensionToken
from app.models.job import Job
from app.schemas.job import JobDescription
from app.services import extension as ext
from app.tasks.jobs import extract_jd
from tests.jobs_helpers import FakeExtractor, make_ctx, make_user

client = TestClient(app)


@pytest.fixture(autouse=True)
def auth():
    app.dependency_overrides[token_claims] = lambda: {"sub": "auth0|A"}
    ext.throttle._hits.clear()


def as_user(sub):
    app.dependency_overrides[token_claims] = lambda: {"sub": sub}


def bearer(token):
    return {"Authorization": f"Bearer {token}"}


def pair(code, **kw):
    return client.post("/extension/pair", json={"code": code, **kw})


def paired(db, sub="auth0|A", device="Chrome"):
    as_user(sub)
    code = client.post("/extension/pair-code").json()["code"]
    return pair(code, device_name=device).json()


CLIP = {
    "url": "https://careers.example.com/jobs/42?utm_source=x",
    "title": "Backend Engineer",
    "company": "Acme",
    "text": "We need a Python engineer to build APIs. " * 5,
}


# --- pairing -----------------------------------------------------------------------
def test_pairing_flow_and_hashes_only_are_stored(db_session):
    make_user(db_session)
    r = client.post("/extension/pair-code")
    assert r.status_code == 200
    code = r.json()["code"]
    assert len(code.replace("-", "")) == 8
    row = db_session.query(ExtensionPairingCode).one()
    assert code not in (row.code_hash, "") and code.replace("-", "") != row.code_hash
    exp = (
        row.expires_at if row.expires_at.tzinfo else row.expires_at.replace(tzinfo=UTC)
    )
    assert timedelta(minutes=9) < exp - datetime.now(UTC) <= timedelta(minutes=10)

    r = pair(code.lower(), device_name="Chrome on laptop")
    assert r.status_code == 200
    body = r.json()
    assert body["token"].startswith("jce_")
    tok = db_session.query(ExtensionToken).one()
    assert tok.token_hash != body["token"] and body["token"] not in tok.token_hash
    assert tok.id == body["token_id"] and tok.device_name == "Chrome on laptop"


def test_pairing_code_is_one_time(db_session):
    make_user(db_session)
    code = client.post("/extension/pair-code").json()["code"]
    assert pair(code).status_code == 200
    r = pair(code)
    assert r.status_code == 401 and r.json()["code"] == "invalid_code"


def test_pairing_code_expires(db_session):
    user = make_user(db_session)
    svc_code = ExtensionPairingCode(
        user_id=user.id,
        code_hash=ext.digest("ABCD2345"),
        expires_at=datetime.now(UTC) - timedelta(seconds=1),
    )
    db_session.add(svc_code)
    db_session.commit()
    r = pair("ABCD-2345")
    assert r.status_code == 401 and r.json()["code"] == "invalid_code"


def test_unknown_code_is_throttled(db_session, monkeypatch):
    from app.core.config import settings

    monkeypatch.setattr(settings, "extension_pair_attempts_per_min", 3)
    assert [pair("WRONG123").status_code for _ in range(3)] == [401, 401, 401]
    assert pair("WRONG123").status_code == 429


# --- token scope ---------------------------------------------------------------------------
def test_device_token_only_works_on_extension_routes(db_session):
    make_user(db_session)
    token = paired(db_session)["token"]
    app.dependency_overrides.pop(token_claims)  # real JWT validation from here on
    for method, path in (
        ("get", "/jobs"),
        ("get", "/recommendations"),
        ("post", "/extension/pair-code"),
        ("get", "/extension/tokens"),
        ("get", "/profile"),
    ):
        r = getattr(client, method)(path, headers=bearer(token))
        assert r.status_code in (401, 503, 404), (path, r.status_code)
        assert r.status_code != 200
    assert (
        client.post("/extension/clip", json=CLIP, headers=bearer(token)).status_code
        == 202
    )


def test_clip_rejects_auth0_style_and_missing_tokens(db_session):
    make_user(db_session)
    app.dependency_overrides.pop(token_claims)
    for h in ({}, bearer("eyJhbGciOiJSUzI1NiJ9.e30.sig"), bearer("jce_nope")):
        r = client.post("/extension/clip", json=CLIP, headers=h)
        assert r.status_code == 401 and r.json()["code"] == "invalid_token"


def test_revocation(db_session):
    make_user(db_session)
    p = paired(db_session)
    h = bearer(p["token"])
    assert client.post("/extension/clip", json=CLIP, headers=h).status_code == 202
    assert client.delete(f"/extension/tokens/{p['token_id']}").status_code == 204
    r = client.post(
        "/extension/clip", json={**CLIP, "text": "other text " * 20}, headers=h
    )
    assert r.status_code == 401
    assert (
        client.delete(f"/extension/tokens/{p['token_id']}").status_code == 204
    )  # idempotent
    listed = client.get("/extension/tokens").json()
    assert (
        listed[0]["revoked_at"]
        and listed[0]["last_used_at"]
        and "token" not in listed[0]
    )


def test_deleting_account_disables_tokens(db_session):
    user = make_user(db_session)
    p = paired(db_session)
    user.status = "deleting"
    db_session.commit()
    assert (
        client.post(
            "/extension/clip", json=CLIP, headers=bearer(p["token"])
        ).status_code
        == 401
    )


# --- clip ---------------------------------------------------------------------------------------
def test_clip_creates_a_clipped_job_and_runs_v1_extraction_on_the_text(
    db_session, tmp_path, queue
):
    user = make_user(db_session)
    p = paired(db_session)
    r = client.post("/extension/clip", json=CLIP, headers=bearer(p["token"]))
    assert r.status_code == 202 and r.json()["status"] == "processing"
    job = db_session.get(Job, r.json()["job_id"])
    assert (job.source_channel, job.user_id, job.source) == ("clipped", user.id, "text")
    assert (
        job.url == "https://careers.example.com/jobs/42"
    )  # reference only, tracking stripped
    assert "Python engineer" in job.raw_text and "Backend Engineer" in job.raw_text
    assert queue.calls == [("extract_jd", {"user_id": str(user.id), "job_id": job.id})]

    # the v1 task runs on the provided text and never fetches the URL
    class NoFetch:
        def fetch(self, url):
            raise AssertionError("server must not fetch the clipped URL")

    ex = FakeExtractor(JobDescription(title="Backend Engineer", must_have=["Python"]))
    extract_jd(
        make_ctx(db_session, tmp_path, extractor=ex, fetcher=NoFetch()), user.id, job.id
    )
    db_session.expire_all()
    assert job.status == "new" and ex.calls and job.title == "Backend Engineer"


def test_clip_duplicate_returns_existing_job(db_session):
    make_user(db_session)
    p = paired(db_session)
    first = client.post("/extension/clip", json=CLIP, headers=bearer(p["token"]))
    again = client.post("/extension/clip", json=CLIP, headers=bearer(p["token"]))
    assert again.status_code == 200 and again.json() == {
        "job_id": first.json()["job_id"],
        "status": None,
        "duplicate": True,
    }
    assert db_session.query(Job).count() == 1


def test_clip_validates_input(db_session):
    make_user(db_session)
    p = paired(db_session)
    h = bearer(p["token"])
    assert (
        client.post(
            "/extension/clip", json={**CLIP, "url": "ftp://x"}, headers=h
        ).status_code
        == 422
    )
    assert (
        client.post("/extension/clip", json={**CLIP, "text": ""}, headers=h).status_code
        == 422
    )


def test_clip_is_rate_limited(db_session, monkeypatch):
    from app.core.config import settings

    monkeypatch.setattr(settings, "jobs_per_hour", 1)
    make_user(db_session)
    p = paired(db_session)
    h = bearer(p["token"])
    assert client.post("/extension/clip", json=CLIP, headers=h).status_code == 202
    r = client.post(
        "/extension/clip",
        json={**CLIP, "url": "https://x.co/2", "text": "different posting " * 10},
        headers=h,
    )
    assert r.status_code == 429 and r.json()["code"] == "rate_limited"


# --- isolation -----------------------------------------------------------------------------------
def test_two_user_isolation(db_session):
    a, b = make_user(db_session, "auth0|A"), make_user(db_session, "auth0|B")
    pa = paired(db_session, "auth0|A")
    pb = paired(db_session, "auth0|B")
    ja = client.post("/extension/clip", json=CLIP, headers=bearer(pa["token"])).json()[
        "job_id"
    ]
    # the same text clipped by B is B's own job, not a duplicate of A's
    jb = client.post("/extension/clip", json=CLIP, headers=bearer(pb["token"])).json()
    assert jb["duplicate"] is False and jb["job_id"] != ja
    assert (
        db_session.get(Job, ja).user_id == a.id
        and db_session.get(Job, jb["job_id"]).user_id == b.id
    )
    # B cannot revoke or list A's device
    as_user("auth0|B")
    r = client.delete(f"/extension/tokens/{pa['token_id']}")
    assert r.status_code == 404 and r.json()["code"] == "not_found"
    assert [t["id"] for t in client.get("/extension/tokens").json()] == [pb["token_id"]]
    assert (
        client.post(
            "/extension/clip",
            json={**CLIP, "url": "https://x.co/other", "text": "again " * 30},
            headers=bearer(pa["token"]),
        ).status_code
        == 202
    )


# --- account deletion -------------------------------------------------------------------------------
def test_delete_user_purges_tokens_recommendations_and_codes(db_session):
    from app.tasks.account import PURGE_ORDER

    names = {m.__table__.name for m in PURGE_ORDER}
    assert {"extension_tokens", "extension_pairing_codes", "recommendations"} <= names
