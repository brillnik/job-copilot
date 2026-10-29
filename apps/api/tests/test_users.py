import pytest
from fastapi.testclient import TestClient

from app.core.security import token_claims
from app.main import app
from app.models.user import User

client = TestClient(app)


def as_user(**claims):
    app.dependency_overrides[token_claims] = lambda: {"sub": "auth0|1"} | claims


@pytest.fixture(autouse=True)
def _clear():
    yield
    app.dependency_overrides.pop(token_claims, None)


def test_first_request_creates_user(db_session):
    as_user(email="a@b.co", name="Ada")
    r = client.get("/me")
    assert r.status_code == 200
    assert r.json()["email"] == "a@b.co"
    assert db_session.query(User).count() == 1


def test_same_sub_reuses_user(db_session):
    as_user()
    first = client.get("/me").json()["id"]
    assert client.get("/me").json()["id"] == first
    assert db_session.query(User).count() == 1


def test_profile_updates_only_from_present_claims(db_session):
    as_user(email="a@b.co", name="Ada")
    client.get("/me")
    as_user(email="new@b.co")  # no name claim: keep the stored one
    body = client.get("/me").json()
    assert body["email"] == "new@b.co"
    assert body["name"] == "Ada"


def test_missing_profile_claims_are_null():
    as_user()
    body = client.get("/me").json()
    assert body["email"] is None and body["name"] is None
