import base64
import json
import time
from urllib.parse import parse_qs, urlparse

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.api.deps import get_google_client
from app.core import signing
from app.core.config import settings
from app.core.security import token_claims
from app.main import app
from app.models.email import EmailEvent, GmailConnection
from app.models.tracker import TrackerCard
from app.repositories.manager import RepositoryManager
from app.services.gmail import make_state, process_new_messages
from app.services.google import GoogleError
from tests.gmail_helpers import (
    EMAIL,
    FakeClassifier,
    FakeGoogle,
    enable,
    msg,
    seed_card,
)
from tests.jobs_helpers import make_user

client = TestClient(app)


def as_user(sub):
    app.dependency_overrides[token_claims] = lambda: {
        "sub": sub,
        "iat": int(time.time()),
    }


@pytest.fixture
def google():
    g = FakeGoogle([msg("m1")])
    app.dependency_overrides[get_google_client] = lambda: g
    return g


@pytest.fixture(autouse=True)
def cfg(monkeypatch):
    monkeypatch.setattr(settings, "google_client_id", "cid")
    monkeypatch.setattr(
        settings, "gmail_redirect_uri", "https://api.test/integrations/gmail/callback"
    )
    monkeypatch.setattr(settings, "gmail_push_secret", "push-secret")
    as_user("auth0|A")


def connect(user):
    state = make_state(user.id)
    r = client.get("/integrations/gmail/callback", params={"code": "c", "state": state})
    assert r.status_code == 200, r.text
    return r


def test_feature_flag_enforced(db_session, google):
    user = make_user(db_session)
    assert client.get("/integrations/gmail").json() == {
        "enabled": False, "connected": False, "needs_reconnect": False,
        "connected_at": None, "last_synced_at": None, "pending_suggestions": 0,
    }  # fmt: skip
    for method, url in [
        ("get", "/integrations/gmail/connect"),
        ("get", "/integrations/gmail/suggestions"),
        ("delete", "/integrations/gmail"),
        ("post", "/integrations/gmail/suggestions/x/accept"),
    ]:
        r = getattr(client, method)(url)
        assert r.status_code == 403 and r.json()["code"] == "feature_disabled", url
    state = make_state(user.id)
    r = client.get("/integrations/gmail/callback", params={"code": "c", "state": state})
    assert r.status_code == 403
    assert db_session.scalars(select(GmailConnection)).all() == []


def test_global_feature_switch(db_session, google, monkeypatch):
    make_user(db_session)
    monkeypatch.setattr(settings, "gmail_feature", True)
    assert client.get("/integrations/gmail").json()["enabled"] is True


def test_connect_url(db_session, google, monkeypatch):
    user = make_user(db_session)
    enable(monkeypatch, user)
    url = client.get("/integrations/gmail/connect").json()["url"]
    q = parse_qs(urlparse(url).query)
    assert url.startswith("https://accounts.google.com/")
    assert q["scope"] == ["https://www.googleapis.com/auth/gmail.readonly"]
    assert q["access_type"] == ["offline"] and q["client_id"] == ["cid"]
    from app.services.gmail import read_state

    assert read_state(q["state"][0]) == user.id


def test_state_is_tamper_proof_and_expires(db_session, google, monkeypatch):
    user = make_user(db_session)
    enable(monkeypatch, user)
    good = make_state(user.id)
    body, mac = good.split(".")
    for bad in ["x.y", body + ".AAAA", "", f"{body}x.{mac}"]:
        r = client.get(
            "/integrations/gmail/callback", params={"code": "c", "state": bad}
        )
        assert r.status_code == 400 and r.json()["code"] == "invalid_state"
    monkeypatch.setattr(signing, "now", lambda: time.time() + 10_000)
    r = client.get("/integrations/gmail/callback", params={"code": "c", "state": good})
    assert r.json()["code"] == "invalid_state"


def test_callback_stores_encrypted_token_and_hashed_address(
    db_session, google, monkeypatch, queue
):
    user = make_user(db_session)
    enable(monkeypatch, user)
    connect(user)
    conn = db_session.scalar(select(GmailConnection))
    assert conn.user_id == user.id and "rt-secret" not in conn.token_ciphertext
    assert EMAIL not in conn.email_hash
    assert queue.names() == ["poll_gmail"]
    st = client.get("/integrations/gmail").json()
    assert st["connected"] and st["enabled"]
    connect(user)  # reconnect upserts
    assert len(db_session.scalars(select(GmailConnection)).all()) == 1


def test_callback_denied(db_session, google, monkeypatch):
    user = make_user(db_session)
    enable(monkeypatch, user)
    r = client.get(
        "/integrations/gmail/callback",
        params={"error": "access_denied", "state": make_state(user.id)},
    )
    assert r.status_code == 400 and r.json()["code"] == "gmail_denied"


def push(token="push-secret", email=EMAIL):
    data = base64.b64encode(
        json.dumps({"emailAddress": email, "historyId": "9"}).encode()
    ).decode()
    return client.post(
        "/integrations/gmail/push",
        params={"token": token} if token else {},
        json={"message": {"data": data, "messageId": "1"}, "subscription": "s"},
    )


def test_push_maps_hash_to_user_and_enqueues_each_time(
    db_session, google, monkeypatch, queue
):
    user = make_user(db_session)
    enable(monkeypatch, user)
    connect(user)
    queue.calls.clear()
    assert push().status_code == 204 and push().status_code == 204
    assert queue.calls == [("poll_gmail", {"user_id": str(user.id)})] * 2
    queue.calls.clear()
    assert push(email="stranger@example.com").status_code == 204
    assert queue.calls == []  # acked, nothing enqueued


def test_push_requires_secret(db_session, google, monkeypatch, queue):
    assert push(token="wrong").status_code == 403
    assert push(token=None).status_code == 403
    monkeypatch.setattr(settings, "gmail_push_secret", "")
    assert push(token="").status_code == 403 and queue.calls == []


def test_repeated_push_then_sync_never_double_moves(
    db_session, google, monkeypatch, queue
):
    user, _, card = seed_card(db_session)
    enable(monkeypatch, user)
    connect(user)
    for _ in range(3):
        push()
        process_new_messages(
            RepositoryManager(db_session),
            google,
            FakeClassifier("interview", 0.9),
            user.id,
        )
    assert len(db_session.scalars(select(EmailEvent)).all()) == 1
    assert [h["to"] for h in db_session.get(TrackerCard, card.id).history].count(
        "interview"
    ) == 1


def test_suggestion_accept_moves_card(db_session, google, monkeypatch):
    user, job, card = seed_card(db_session)
    enable(monkeypatch, user)
    connect(user)
    process_new_messages(
        RepositoryManager(db_session), google, FakeClassifier("offer", 0.6), user.id
    )
    (s,) = client.get("/integrations/gmail/suggestions").json()
    assert s["suggested_column"] == "offer" and s["company"] == job.company
    assert s["status"] == "pending" and "subject" not in s
    assert client.get("/integrations/gmail").json()["pending_suggestions"] == 1
    r = client.post(f"/integrations/gmail/suggestions/{s['id']}/accept")
    assert r.status_code == 200 and r.json()["status"] == "accepted"
    assert db_session.get(TrackerCard, card.id).column == "offer"
    assert (
        client.post(f"/integrations/gmail/suggestions/{s['id']}/accept").status_code
        == 200
    )
    assert (
        client.post(f"/integrations/gmail/suggestions/{s['id']}/dismiss").status_code
        == 409
    )
    assert client.get("/integrations/gmail/suggestions").json() == []


def test_suggestion_dismiss_leaves_card(db_session, google, monkeypatch):
    user, _, card = seed_card(db_session)
    enable(monkeypatch, user)
    connect(user)
    process_new_messages(
        RepositoryManager(db_session), google, FakeClassifier("interview", 0.5), user.id
    )
    (s,) = client.get("/integrations/gmail/suggestions").json()
    r = client.post(f"/integrations/gmail/suggestions/{s['id']}/dismiss")
    assert r.json()["status"] == "dismissed"
    assert db_session.get(TrackerCard, card.id).column == "applied"
    assert (
        client.post(f"/integrations/gmail/suggestions/{s['id']}/accept").status_code
        == 409
    )


def test_isolation_between_users(db_session, google, monkeypatch):
    a, _, card = seed_card(db_session)
    b = make_user(db_session, "auth0|B")
    enable(monkeypatch, a, b)
    connect(a)
    process_new_messages(
        RepositoryManager(db_session), google, FakeClassifier("interview", 0.5), a.id
    )
    as_user("auth0|A")
    (s,) = client.get("/integrations/gmail/suggestions").json()
    as_user("auth0|B")
    assert client.get("/integrations/gmail/suggestions").json() == []
    assert client.get("/integrations/gmail").json()["connected"] is False
    for action in ("accept", "dismiss"):
        r = client.post(f"/integrations/gmail/suggestions/{s['id']}/{action}")
        assert r.status_code == 404
    assert db_session.get(TrackerCard, card.id).column == "applied"
    client.delete("/integrations/gmail")  # B disconnecting touches nothing of A's
    assert db_session.scalars(select(EmailEvent)).all() != []
    assert db_session.scalar(select(GmailConnection)) is not None


def test_disconnect_revokes_and_deletes_everything(db_session, google, monkeypatch):
    user, _, _ = seed_card(db_session)
    enable(monkeypatch, user)
    connect(user)
    process_new_messages(
        RepositoryManager(db_session), google, FakeClassifier("interview", 0.5), user.id
    )
    assert db_session.scalars(select(EmailEvent)).all()
    assert client.delete("/integrations/gmail").status_code == 204
    assert google.revoked == ["rt-secret"]
    assert db_session.scalars(select(EmailEvent)).all() == []
    assert db_session.scalars(select(GmailConnection)).all() == []
    assert client.delete("/integrations/gmail").status_code == 204  # idempotent


def test_disconnect_still_deletes_when_google_is_down(db_session, google, monkeypatch):
    user = make_user(db_session)
    enable(monkeypatch, user)
    connect(user)
    google.revoke_error = GoogleError("down")
    assert client.delete("/integrations/gmail").status_code == 204
    assert db_session.scalars(select(GmailConnection)).all() == []


def test_account_deletion_and_export_cover_gmail_tables(
    db_session, google, monkeypatch, tmp_path
):
    import io
    import zipfile

    from app.tasks import account as acct
    from tests.jobs_helpers import make_ctx

    user, _, _ = seed_card(db_session)
    enable(monkeypatch, user)
    connect(user)
    process_new_messages(
        RepositoryManager(db_session),
        google,
        FakeClassifier("interview", 0.95),
        user.id,
    )
    ctx = make_ctx(db_session, tmp_path)
    data = acct.build_export(ctx, RepositoryManager(db_session), user)
    with zipfile.ZipFile(io.BytesIO(data)) as z:
        rows = json.loads(z.read("email_events.json"))
    assert len(rows) == 1 and "subject" not in rows[0]
    acct.purge_data(db_session, user.id)
    assert db_session.scalars(select(EmailEvent)).all() == []
    assert db_session.scalars(select(GmailConnection)).all() == []
