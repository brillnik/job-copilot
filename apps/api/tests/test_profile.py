import pytest
from fastapi.testclient import TestClient

from app.api.deps import get_extractor
from app.core.security import token_claims
from app.main import app
from app.schemas.profile import Bullet, Contact, Experience, ProfileData

client = TestClient(app)

PDF = b"%PDF-1.7\nhello"


def _data():
    return ProfileData(
        contact=Contact(name="Ada"),
        experience=[
            Experience(
                id="e1",
                company="Acme",
                title="Engineer",
                bullets=[
                    Bullet(
                        id="b1", text="Built Kafka pipelines processing 2M events/day"
                    ),
                    Bullet(id="b2", text="Led migration of Postgres to Aurora"),
                    Bullet(id="b3", text="Mentored four junior engineers"),
                ],
            )
        ],
    )


class FakeExtractor:
    def extract(self, filename, data):
        return _data()


@pytest.fixture(autouse=True)
def auth():
    app.dependency_overrides[token_claims] = lambda: {"sub": "auth0|1"}
    app.dependency_overrides[get_extractor] = lambda: FakeExtractor()


def test_requires_auth():
    app.dependency_overrides.pop(token_claims)
    assert client.get("/profile").status_code in (401, 503)


def test_empty_states():
    assert client.get("/profile").status_code == 404
    assert client.get("/profile/draft").status_code == 404
    assert client.post("/profile/approve").status_code == 404
    assert client.post("/profile/bullets", json={"queries": ["x"]}).status_code == 404


def test_upload_creates_draft():
    r = client.post("/profile/upload", files={"file": ("cv.pdf", PDF)})
    assert r.status_code == 201
    body = r.json()
    assert body["status"] == "draft" and body["resume_id"]
    assert body["data"]["experience"][0]["bullets"][0]["id"] == "b1"
    assert client.get("/profile/draft").json()["id"] == body["id"]


def test_upload_rejects_bad_file():
    r = client.post("/profile/upload", files={"file": ("cv.pdf", b"nope")})
    assert r.status_code == 415
    assert client.get("/profile/draft").status_code == 404


def test_put_draft_assigns_ids_and_replaces():
    r = client.put("/profile/draft", json={"summary": "hi", "skills": ["go"]})
    assert r.status_code == 200
    again = client.put(
        "/profile/draft",
        json={"experience": [{"company": "X", "bullets": [{"text": "did a thing"}]}]},
    )
    assert again.json()["id"] == r.json()["id"]
    bullet = again.json()["data"]["experience"][0]["bullets"][0]
    assert len(bullet["id"]) == 32
    assert again.json()["data"]["skills"] == []


def test_approve_versions_and_search():
    client.post("/profile/upload", files={"file": ("cv.pdf", PDF)})
    r = client.post("/profile/approve")
    assert r.status_code == 200
    assert r.json()["status"] == "approved" and r.json()["version"] == 1
    assert client.get("/profile/draft").status_code == 404
    assert client.get("/profile").json()["version"] == 1

    found = client.post(
        "/profile/bullets",
        json={"queries": ["Kafka streaming", "Postgres migration"], "per_query": 1},
    ).json()
    assert found["profile_version"] == 1
    assert [b["source_id"] for b in found["bullets"]] == ["b1", "b2"] or {
        b["source_id"] for b in found["bullets"]
    } == {"b1", "b2"}
    assert found["bullets"][0]["matched_queries"]

    # Editing starts a new draft; the approved version stays until re-approved.
    client.put("/profile/draft", json={"summary": "v2"})
    assert client.get("/profile").json()["version"] == 1
    assert client.post("/profile/approve").json()["version"] == 2


def test_search_diversity_cap():
    client.post("/profile/upload", files={"file": ("cv.pdf", PDF)})
    client.post("/profile/approve")
    found = client.post(
        "/profile/bullets",
        json={
            "queries": ["Kafka Postgres engineers"],
            "per_query": 10,
            "max_per_entry": 1,
        },
    ).json()
    assert len(found["bullets"]) == 1


def test_users_are_isolated():
    client.post("/profile/upload", files={"file": ("cv.pdf", PDF)})
    client.post("/profile/approve")
    app.dependency_overrides[token_claims] = lambda: {"sub": "auth0|2"}
    assert client.get("/profile").status_code == 404
    assert (
        client.post("/profile/bullets", json={"queries": ["Kafka"]}).status_code == 404
    )


class _V2Embedder:
    name = "v2"
    min_score = 0.5

    def embed_documents(self, texts):
        return [[1.0, 0.0] for _ in texts]

    def embed_queries(self, texts):
        return [[1.0, 0.0] for _ in texts]


def test_search_reembeds_when_embedder_changes(db_session):
    from app.api.deps import get_embedder
    from app.models.profile import ProfileBullet

    client.post("/profile/upload", files={"file": ("cv.pdf", PDF)})
    client.post("/profile/approve")  # indexed with the hashing embedder
    app.dependency_overrides[get_embedder] = lambda: _V2Embedder()
    found = client.post("/profile/bullets", json={"queries": ["anything"]}).json()
    assert len(found["bullets"]) == 3
    rows = db_session.query(ProfileBullet).all()
    assert {r.embedding_model for r in rows} == {"v2"}


def test_min_score_filters_noise():
    client.post("/profile/upload", files={"file": ("cv.pdf", PDF)})
    client.post("/profile/approve")
    found = client.post("/profile/bullets", json={"queries": ["zzz qqq"]}).json()
    assert found["bullets"] == []
