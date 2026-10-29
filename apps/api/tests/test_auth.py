import time

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi.testclient import TestClient

from app.core import security
from app.core.config import settings
from app.main import app

DOMAIN = "tenant.example.auth0.com"
AUDIENCE = "https://api.test"
KEY = rsa.generate_private_key(public_exponent=65537, key_size=2048)

client = TestClient(app)


@pytest.fixture(autouse=True)
def configured(monkeypatch):
    monkeypatch.setattr(settings, "auth0_domain", DOMAIN)
    monkeypatch.setattr(settings, "auth0_audience", AUDIENCE)
    monkeypatch.setattr(security, "get_signing_key", lambda _token: KEY.public_key())


def token(**overrides):
    now = int(time.time())
    claims = {
        "sub": "auth0|123",
        "iss": f"https://{DOMAIN}/",
        "aud": AUDIENCE,
        "iat": now,
        "exp": now + 300,
    } | overrides
    return jwt.encode(claims, KEY, algorithm="RS256")


def get_me(tok=None):
    headers = {"Authorization": f"Bearer {tok}"} if tok else {}
    return client.get("/me", headers=headers)


def test_valid_token():
    r = get_me(token())
    assert r.status_code == 200
    assert r.json()["auth0_sub"] == "auth0|123"


def test_missing_token():
    assert get_me().status_code == 401


@pytest.mark.parametrize(
    "overrides",
    [
        {"exp": int(time.time()) - 10},
        {"aud": "https://other"},
        {"iss": "https://evil.example/"},
    ],
)
def test_rejected_claims(overrides):
    assert get_me(token(**overrides)).status_code == 401


def test_wrong_signature():
    other = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    bad = jwt.encode({"sub": "x"}, other, algorithm="RS256")
    assert get_me(bad).status_code == 401


def test_unconfigured(monkeypatch):
    monkeypatch.setattr(settings, "auth0_domain", "")
    assert get_me(token()).status_code == 503
