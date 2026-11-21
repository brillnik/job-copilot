from fastapi.testclient import TestClient
from sqlalchemy import select

from app.core.security import token_claims
from app.main import app
from app.models.training import TrainingConsentLog
from app.tasks import account as acct
from tests.jobs_helpers import make_user

client = TestClient(app)


def as_user(sub):
    app.dependency_overrides[token_claims] = lambda: {"sub": sub}


def test_default_is_not_consented(db_session):
    make_user(db_session, "auth0|A")
    as_user("auth0|A")
    assert client.get("/me/training-consent").json() == {
        "enabled": False,
        "policy_version": None,
        "at": None,
    }


def test_put_appends_and_latest_row_is_current(db_session):
    user = make_user(db_session, "auth0|A")
    as_user("auth0|A")
    for enabled, version in ((True, "v1"), (False, "v1"), (True, "v2")):
        r = client.put(
            "/me/training-consent", json={"enabled": enabled, "policy_version": version}
        )
        assert r.status_code == 200 and r.json()["enabled"] is enabled
    rows = db_session.scalars(
        select(TrainingConsentLog)
        .where(TrainingConsentLog.user_id == user.id)
        .order_by(TrainingConsentLog.id)
    ).all()
    assert [(r.enabled, r.policy_version) for r in rows] == [
        (True, "v1"),
        (False, "v1"),
        (True, "v2"),
    ]
    got = client.get("/me/training-consent").json()
    assert got["enabled"] is True and got["policy_version"] == "v2"


def test_repeating_the_same_state_does_not_append(db_session):
    make_user(db_session, "auth0|A")
    as_user("auth0|A")
    body = {"enabled": True, "policy_version": "v1"}
    client.put("/me/training-consent", json=body)
    client.put("/me/training-consent", json=body)
    assert len(db_session.scalars(select(TrainingConsentLog)).all()) == 1


def test_validation(db_session):
    make_user(db_session, "auth0|A")
    as_user("auth0|A")
    assert client.put("/me/training-consent", json={"enabled": True}).status_code == 422
    r = client.put("/me/training-consent", json={"enabled": "x", "policy_version": "1"})
    assert r.status_code == 422


def test_consent_is_per_user(db_session):
    make_user(db_session, "auth0|A")
    make_user(db_session, "auth0|B")
    as_user("auth0|A")
    client.put("/me/training-consent", json={"enabled": True, "policy_version": "v1"})
    as_user("auth0|B")
    assert client.get("/me/training-consent").json()["enabled"] is False
    client.put("/me/training-consent", json={"enabled": False, "policy_version": "v1"})
    as_user("auth0|A")
    assert client.get("/me/training-consent").json()["enabled"] is True


def test_requires_auth(db_session):
    app.dependency_overrides.pop(token_claims, None)
    assert client.get("/me/training-consent").status_code in (401, 403)


def test_consent_log_is_purged_on_account_deletion():
    assert TrainingConsentLog in acct.PURGE_ORDER
