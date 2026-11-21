from datetime import timedelta

import pytest
from fastapi.testclient import TestClient

from app.ai.embeddings import HashingEmbedder
from app.core.clock import local_day
from app.core.config import settings
from app.core.security import token_claims
from app.main import app
from app.models.discovery import Recommendation
from app.models.job import Job
from app.repositories.manager import RepositoryManager
from app.services.recommendation import build_recommendations, profile_vector
from app.vector.index import BruteForceIndex, SearchFilters
from tests.discovery_helpers import NOW, jd_for, make_catalog
from tests.jobs_helpers import Boom, approve_profile, make_ctx, make_user

client = TestClient(app)


@pytest.fixture(autouse=True)
def auth():
    app.dependency_overrides[token_claims] = lambda: {"sub": "auth0|A"}


def as_user(sub):
    app.dependency_overrides[token_claims] = lambda: {"sub": sub}


def seed(db, sub="auth0|A", cities=()):
    user = make_user(db, sub)
    approve_profile(db, user)
    if cities:
        user.preferences = {"cities": list(cities)}
        db.commit()
    return user


def build(db, tmp_path, user, **kw):
    ctx = make_ctx(db, tmp_path, extractor=Boom())  # an LLM call would raise
    kw.setdefault("now", NOW)
    return build_recommendations(ctx, user.id, **kw)


def digest(db, user):
    return RepositoryManager(db).recommendations.digest(user.id, local_day(NOW))


# --- vector index ------------------------------------------------------------------
def test_brute_force_index_ranks_by_cosine_and_applies_filters():
    ix = BruteForceIndex()
    base = {
        "closed_at": None,
        "first_seen": NOW,
        "remote": False,
        "country_restrictions": [],
        "city": "Pune",
    }
    ix.upsert("near", [1, 0], base)
    ix.upsert("far", [0, 1], base)
    ix.upsert("closed", [1, 0], base | {"closed_at": NOW})
    ix.upsert("old", [1, 0], base | {"first_seen": NOW - timedelta(days=60)})
    ix.upsert(
        "remote_us",
        [1, 0],
        base
        | {"city": None, "remote": True, "country_restrictions": ["United States"]},
    )
    ix.upsert(
        "remote_in",
        [1, 0],
        base | {"city": None, "remote": True, "country_restrictions": ["India"]},
    )
    ix.upsert("remote_any", [1, 0], base | {"city": None, "remote": True})
    ix.upsert("blr", [1, 0], base | {"city": "Bengaluru"})
    f = SearchFilters(
        first_seen_after=NOW - timedelta(days=21), cities=("Pune",), country="India"
    )
    ids = [h.id for h in ix.search([2, 0], 10, f)]
    assert ids[-1] == "far"  # orthogonal vector ranks last
    assert set(ids) == {"near", "far", "remote_in", "remote_any"}
    assert ix.search([1, 0], 1, f)[0].score == pytest.approx(1.0)
    ix.remove("near")
    assert "near" not in {h.id for h in ix.search([1, 0], 10, f)}


def test_index_without_cities_does_not_filter_by_location():
    ix = BruteForceIndex()
    ix.upsert(
        "a",
        [1, 0],
        {"closed_at": None, "first_seen": NOW, "remote": False, "city": "Pune"},
    )
    assert [h.id for h in ix.search([1, 0], 5, SearchFilters())] == ["a"]


# --- build_recommendations -------------------------------------------------------------------
def test_digest_is_top_n_by_score_with_reasons_from_the_breakdown(
    db_session, tmp_path, monkeypatch
):
    monkeypatch.setattr(settings, "reco_digest_size", 2)
    user = seed(db_session)
    make_catalog(
        db_session,
        title="Python Postgres Dev",
        external_id="1",
        jd=jd_for("Python Postgres Dev"),
    )
    make_catalog(
        db_session,
        title="Rust Dev",
        external_id="2",
        jd=jd_for("Rust Dev", must=("Rust", "C++")),
    )
    make_catalog(
        db_session,
        title="Python Dev",
        external_id="3",
        jd=jd_for("Python Dev", must=("Python",)),
    )
    assert build(db_session, tmp_path, user) == 2
    recs = digest(db_session, user)
    assert len(recs) == 2 and recs[0].score >= recs[1].score
    titles = {
        db_session.get(type(r).__mapper__.class_, r.id).catalog_job_id for r in recs
    }
    assert len(titles) == 2
    top = recs[0]
    assert top.reasons and top.reasons[0].startswith("Matches ")
    assert top.digest_date == local_day(NOW) and top.action == "none"


def test_zero_llm_calls(db_session, tmp_path):
    user = seed(db_session)
    make_catalog(db_session, title="Dev", external_id="1")
    ctx = make_ctx(
        db_session, tmp_path, extractor=Boom(), transcriber=Boom(), fetcher=Boom()
    )
    assert build_recommendations(ctx, user.id, now=NOW) == 1  # Boom() would have raised


def test_filters_closed_old_duplicates_unenriched_and_wrong_location(
    db_session, tmp_path
):
    user = seed(db_session, cities=["Bengaluru"])
    good = make_catalog(db_session, title="Good", external_id="g")
    make_catalog(db_session, title="Closed", external_id="c", closed_at=NOW)
    make_catalog(
        db_session, title="Old", external_id="o", first_seen=NOW - timedelta(days=30)
    )
    make_catalog(db_session, title="Dup", external_id="d", duplicate_of=good.id)
    make_catalog(db_session, title="NoVector", external_id="n", embed=False)
    make_catalog(db_session, title="Pune", external_id="p", city="Pune")
    make_catalog(
        db_session,
        title="RemoteIN",
        external_id="ri",
        city=None,
        remote=True,
        restrictions=["India"],
    )
    make_catalog(
        db_session,
        title="RemoteUS",
        external_id="ru",
        city=None,
        remote=True,
        restrictions=["United States"],
    )
    assert build(db_session, tmp_path, user) == 2
    got = {
        db_session.get(Recommendation, r.id).catalog_job_id
        for r in digest(db_session, user)
    }
    cj = RepositoryManager(db_session).catalog
    assert {cj.by_id(i).title for i in got} == {"Good", "RemoteIN"}


def test_vectors_from_another_embedder_are_ignored(db_session, tmp_path):
    user = seed(db_session)
    row = make_catalog(db_session, title="Dev", external_id="1")
    row.embedding_model = "someone-else"
    db_session.commit()
    assert build(db_session, tmp_path, user) == 0


def test_saved_dismissed_and_owned_jobs_are_excluded(db_session, tmp_path):
    user = seed(db_session)
    a = make_catalog(db_session, title="A", external_id="a")
    b = make_catalog(db_session, title="B", external_id="b")
    c = make_catalog(db_session, title="C", external_id="c")
    d = make_catalog(db_session, title="D", external_id="d")
    repos = RepositoryManager(db_session)
    old = (NOW - timedelta(days=3)).strftime("%Y-%m-%d")
    db_session.add_all(
        [
            Recommendation(
                user_id=user.id,
                catalog_job_id=a.id,
                score=50,
                digest_date=old,
                action="saved",
            ),
            Recommendation(
                user_id=user.id,
                catalog_job_id=b.id,
                score=50,
                digest_date=old,
                action="dismissed",
            ),
            Job(user_id=user.id, source="text", status="new", catalog_job_id=c.id),
        ]
    )
    db_session.commit()
    assert build(db_session, tmp_path, user) == 1
    (rec,) = digest(db_session, user)
    assert rec.catalog_job_id == d.id and repos.catalog.by_id(a.id)


def test_rebuild_is_idempotent_and_keeps_acted_rows(db_session, tmp_path):
    user = seed(db_session)
    make_catalog(db_session, title="A", external_id="a")
    make_catalog(db_session, title="B", external_id="b")
    build(db_session, tmp_path, user)
    first = digest(db_session, user)
    first[0].action = "saved"
    db_session.commit()
    saved = first[0].catalog_job_id
    build(db_session, tmp_path, user)
    rows = digest(db_session, user)
    assert len(rows) == 2 and {r.catalog_job_id for r in rows} >= {saved}


def test_no_profile_or_unknown_user_builds_nothing(db_session, tmp_path):
    user = make_user(db_session)
    make_catalog(db_session, title="A", external_id="a")
    assert build(db_session, tmp_path, user) == 0


def test_works_with_a_fake_vector_index(db_session, tmp_path):
    user = seed(db_session)
    row = make_catalog(db_session, title="A", external_id="a")
    make_catalog(db_session, title="B", external_id="b")

    class Fake:
        def search(self, vector, k, filters):
            from app.vector.index import Hit

            return [Hit(row.id, 0.9)]

    assert build(db_session, tmp_path, user, index=Fake()) == 1


def test_profile_vector_is_cached_per_profile_version(db_session):
    user = seed(db_session)
    repos = RepositoryManager(db_session)

    class Counting(HashingEmbedder):
        calls = 0

        def embed_queries(self, texts):
            Counting.calls += 1
            return super().embed_queries(texts)

    emb = Counting()
    v1 = profile_vector(repos, emb, user.id)
    assert profile_vector(repos, emb, user.id) == v1 and Counting.calls == 1


# --- API ------------------------------------------------------------------------------------------
def test_get_save_dismiss_flow(db_session, tmp_path, queue):
    user = seed(db_session)
    make_catalog(
        db_session,
        title="Dev",
        external_id="1",
        source="himalayas",
        remote=True,
        city=None,
    )
    make_catalog(
        db_session, title="Ops", external_id="2", jd=jd_for("Ops", must=("Terraform",))
    )
    build_recommendations(make_ctx(db_session, tmp_path, extractor=Boom()), user.id)
    items = client.get("/recommendations").json()["items"]
    assert len(items) == 2
    him = next(i for i in items if i["title"] == "Dev")
    assert him["source_attribution"]["provider"] == "Himalayas"
    assert (
        him["apply_url"].startswith("https://example.com/apply/")
        and him["company"] == "Acme"
    )

    # save -> a v1 job from the catalogue JD, no extractor, scored
    r = client.post(f"/recommendations/{him['id']}/save")
    assert r.status_code == 200 and r.json()["action"] == "saved"
    job = db_session.get(Job, r.json()["job_id"])
    assert (job.source_channel, job.catalog_job_id, job.status) == (
        "recommended",
        him["catalog_job_id"],
        "new",
    )
    assert job.url == him["apply_url"] and job.score is not None
    assert [m["skill"] for m in job.musts] == ["Python", "Postgres"]
    assert job.company == "Acme" and not queue.calls  # nothing queued: no extraction
    detail = client.get(f"/jobs/{job.id}").json()
    assert detail["jd"]["must_have"] == ["Python", "Postgres"]
    # idempotent
    assert client.post(f"/recommendations/{him['id']}/save").json()["job_id"] == job.id
    assert (
        db_session.query(Job)
        .filter(Job.catalog_job_id == him["catalog_job_id"])
        .count()
        == 1
    )

    # dismiss
    ops = next(i for i in items if i["title"] == "Ops")
    r = client.post(
        f"/recommendations/{ops['id']}/dismiss", json={"reason": "not my stack"}
    )
    assert r.status_code == 200 and r.json()["action"] == "dismissed"
    assert [i["id"] for i in client.get("/recommendations").json()["items"]] == [
        him["id"]
    ]
    assert client.post(f"/recommendations/{ops['id']}/dismiss").status_code == 200
    assert (
        client.post(f"/recommendations/{him['id']}/dismiss").json()["code"]
        == "invalid_state"
    )
    stored = db_session.get(Recommendation, ops["id"])
    assert stored.dismiss_reason == "not my stack"


def test_save_runs_the_v1_scorer_and_never_the_extractor(db_session, tmp_path):
    from app.services.recommendation import RecommendationService, ScoringContext
    from app.tasks.jobs import scoring_config

    user = seed(db_session)
    row = make_catalog(db_session, title="Dev", external_id="1")
    rec = Recommendation(
        user_id=user.id, catalog_job_id=row.id, score=80, digest_date=local_day()
    )
    db_session.add(rec)
    db_session.commit()
    svc = RecommendationService(
        RepositoryManager(db_session),
        Boom(),
        ScoringContext(scoring_config(), HashingEmbedder()),
    )
    out = svc.save(user.id, rec.id)  # Boom() as queue: enqueueing would raise
    assert out.job_id and db_session.get(Job, out.job_id).score is not None


def test_empty_digest_and_unknown_id(db_session):
    seed(db_session)
    assert client.get("/recommendations").json() == {"items": []}
    r = client.post("/recommendations/nope/save")
    assert r.status_code == 404 and r.json()["code"] == "not_found"


def test_two_user_isolation(db_session, tmp_path):
    a = seed(db_session, "auth0|A")
    b = seed(db_session, "auth0|B")
    make_catalog(db_session, title="Dev", external_id="1")
    ctx = make_ctx(db_session, tmp_path, extractor=Boom())
    build_recommendations(ctx, a.id)
    build_recommendations(ctx, b.id)
    as_user("auth0|A")
    a_item = client.get("/recommendations").json()["items"][0]
    as_user("auth0|B")
    b_item = client.get("/recommendations").json()["items"][0]
    assert a_item["id"] != b_item["id"]
    # B cannot touch A's recommendation
    for path in ("save", "dismiss"):
        r = client.post(f"/recommendations/{a_item['id']}/{path}")
        assert r.status_code == 404 and r.json()["code"] == "not_found"
    db_session.expire_all()
    assert db_session.get(Recommendation, a_item["id"]).action == "none"
    assert db_session.query(Job).filter(Job.user_id == b.id).count() == 0
    # A's dismissal does not hide B's item
    as_user("auth0|A")
    client.post(f"/recommendations/{a_item['id']}/dismiss")
    as_user("auth0|B")
    assert len(client.get("/recommendations").json()["items"]) == 1
    # A's saved job is invisible to B
    as_user("auth0|A")
    other = client.post(f"/recommendations/{b_item['id']}/save")
    assert other.status_code == 404
