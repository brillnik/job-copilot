import pytest
from fastapi.testclient import TestClient

from app.core.config import settings
from app.core.security import token_claims
from app.main import app
from app.models.resume import Resume
from app.models.user import User

client = TestClient(app)

PDF = b"%PDF-1.7\nhello"
DOCX = b"PK\x03\x04rest-of-zip"


@pytest.fixture(autouse=True)
def auth(monkeypatch):
    monkeypatch.setattr(settings, "max_resume_bytes", 1024)
    app.dependency_overrides[token_claims] = lambda: {
        "sub": "auth0|123",
        "email": "a@b.co",
    }


def upload(name, content):
    return client.post("/resumes", files={"file": (name, content)})


@pytest.mark.parametrize("name,content", [("cv.pdf", PDF), ("CV.DOCX", DOCX)])
def test_upload_ok(name, content, tmp_path, db_session):
    r = upload(name, content)
    assert r.status_code == 201
    body = r.json()
    assert body["filename"] == name
    assert body["size"] == len(content)

    row = db_session.get(Resume, body["id"])
    assert db_session.get(User, row.user_id).auth0_sub == "auth0|123"
    assert (tmp_path / row.storage_key).read_bytes() == content


def test_requires_auth():
    app.dependency_overrides.pop(token_claims)
    assert upload("cv.pdf", PDF).status_code in (401, 503)


def test_bad_extension():
    assert upload("cv.exe", PDF).status_code == 415


def test_content_mismatch():
    assert upload("cv.pdf", b"not a pdf").status_code == 415


def test_empty():
    assert upload("cv.pdf", b"").status_code == 400


def test_too_large(tmp_path, db_session):
    assert upload("cv.pdf", PDF + b"x" * 2048).status_code == 413
    assert list(tmp_path.rglob("*.pdf")) == []
    assert db_session.query(Resume).count() == 0


def test_path_traversal_filename_is_not_used(tmp_path):
    r = upload("../../evil.pdf", PDF)
    assert r.status_code == 201
    assert all(
        tmp_path.resolve() in p.resolve().parents for p in tmp_path.rglob("*.pdf")
    )
