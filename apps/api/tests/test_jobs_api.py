import pytest
from fastapi.testclient import TestClient

from app.core.config import settings
from app.core.security import token_claims
from app.main import app
from app.models.job import Job
from app.schemas.job import JobDescription
from tests.jobs_helpers import approve_profile, make_job, make_user

client = TestClient(app)
PNG = b"\x89PNG\r\n\x1a\n" + b"0" * 20


@pytest.fixture(autouse=True)
def auth():
    app.dependency_overrides[token_claims] = lambda: {"sub": "auth0|A"}


def as_user(sub):
    app.dependency_overrides[token_claims] = lambda: {"sub": sub}


def add(**body):
    return client.post("/jobs", json=body)


# --- POST /jobs ---------------------------------------------------------------
def test_add_text_returns_202_and_enqueues(queue):
    r = add(source="text", text="We need a Python dev")
    assert r.status_code == 202
    body = r.json()
    assert body["status"] == "processing" and body["duplicate"] is False
    assert queue.calls[0][0] == "extract_jd"
    assert queue.calls[0][1]["job_id"] == body["job_id"]


def test_add_url(queue):
    r = add(source="url", url="https://boards.greenhouse.io/acme/jobs/123")
    assert r.status_code == 202
    assert queue.names() == ["extract_jd"]


def test_add_image(queue):
    img = client.post("/jobs/images", files={"file": ("s.png", PNG)})
    assert img.status_code == 201
    r = add(source="image", image_id=img.json()["image_id"])
    assert r.status_code == 202


def test_image_upload_validates_type():
    assert (
        client.post("/jobs/images", files={"file": ("s.png", b"nope")}).status_code
        == 415
    )
    assert (
        client.post("/jobs/images", files={"file": ("s.png", b"")}).status_code == 400
    )


@pytest.mark.parametrize(
    "body",
    [
        {"source": "url"},
        {"source": "url", "url": "ftp://x.com/a"},
        {"source": "url", "url": "https://x.com/a", "text": "also text"},
        {"source": "text", "url": "https://x.com/a"},
        {"source": "text"},
        {"source": "text", "text": "   "},
        {"source": "image"},
        {"source": "image", "text": "x"},
        {"source": "image", "image_id": "abc", "url": "https://x.com"},
        {"source": "pigeon", "text": "x"},
        {},
    ],
)
def test_bad_combinations_are_422(body, queue):
    r = add(**body)
    assert r.status_code == 422
    assert r.json()["code"] == "validation_error"
    assert queue.calls == []


def test_unknown_or_foreign_image_is_404():
    assert add(source="image", image_id="nope").status_code == 404
    img = client.post("/jobs/images", files={"file": ("s.png", PNG)}).json()["image_id"]
    as_user("auth0|B")
    assert add(source="image", image_id=img).status_code == 404


def test_duplicate_by_normalised_url(queue):
    first = add(
        source="url", url="https://Jobs.Example.com/role/7/?utm_source=x&gclid=1"
    ).json()
    r = add(source="url", url="https://jobs.example.com/role/7#apply")
    assert r.status_code == 200
    assert r.json() == {"job_id": first["job_id"], "status": None, "duplicate": True}
    assert queue.names() == ["extract_jd"]  # nothing enqueued for the duplicate
    # a different meaningful query param is a different job
    assert (
        add(source="url", url="https://jobs.example.com/role/7?id=2").status_code == 202
    )


def test_duplicate_by_text_hash():
    first = add(source="text", text="Senior  Python\nDeveloper wanted").json()
    r = add(source="text", text="senior python developer   wanted ")
    assert r.status_code == 200 and r.json()["job_id"] == first["job_id"]


def test_duplicates_are_per_user():
    add(source="text", text="same posting")
    as_user("auth0|B")
    assert add(source="text", text="same posting").status_code == 202


def test_rate_limit(monkeypatch, queue):
    monkeypatch.setattr(settings, "jobs_per_hour", 2)
    assert add(source="text", text="one").status_code == 202
    assert add(source="text", text="two").status_code == 202
    assert add(source="text", text="one").status_code == 200  # duplicates are free
    r = add(source="text", text="three")
    assert r.status_code == 429 and r.json()["code"] == "rate_limited"
    as_user("auth0|B")  # limit is per user
    assert add(source="text", text="three").status_code == 202


def test_error_shape_is_uniform():
    r = client.get("/jobs/nope")
    assert set(r.json()) == {"code", "message", "details"}
    app.dependency_overrides.pop(token_claims)
    r = client.get("/jobs")
    assert r.status_code in (401, 503) and {"code", "message"} <= set(r.json())


# --- GET /jobs ----------------------------------------------------------------
@pytest.fixture
def seeded(db_session):
    user = make_user(db_session)
    rows = [
        ("Acme", "Backend Engineer", 80, "new", "Bengaluru, India", 20, 30),
        ("Globex", "Data Engineer", 55, "new", "Pune", None, None),
        ("Initech", "SRE", None, "processing", None, None, None),
        ("Umbrella", "Backend Developer", 95, "archived", "Bengaluru", None, None),
        ("Hooli", "Frontend Engineer", 30, "in_review", "Mumbai", 10, 15),
    ]
    jobs = []
    for company, title, score, status, loc, lo, hi in rows:
        jd = JobDescription(
            company=company, title=title, location=loc, ctc_lpa_min=lo, ctc_lpa_max=hi,
            must_have=["a", "b"],
        )  # fmt: skip
        job = make_job(db_session, user, jd if loc or lo else None, company=company,
                       title=title, score=score, status=status,
                       musts=[{"skill": "a", "status": "have"}, {"skill": "b", "status": "missing"}])  # fmt: skip
        jobs.append(job)
    return user, jobs


def names(r):
    return [i["company"] for i in r.json()["items"]]


def test_list_default_hides_archived_and_sorts_by_created(seeded):
    r = client.get("/jobs")
    assert r.status_code == 200
    assert sorted(names(r)) == ["Acme", "Globex", "Hooli", "Initech"]


def test_list_filters(seeded):
    assert names(client.get("/jobs?status=archived")) == ["Umbrella"]
    assert names(client.get("/jobs?status=in_review")) == ["Hooli"]
    assert sorted(names(client.get("/jobs?min_score=50"))) == ["Acme", "Globex"]
    assert names(client.get("/jobs?city=bengaluru")) == ["Acme"]
    assert sorted(names(client.get("/jobs?q=engineer"))) == ["Acme", "Globex", "Hooli"]
    assert names(client.get("/jobs?q=GLOBEX")) == ["Globex"]
    assert names(client.get("/jobs?q=engineer&min_score=70")) == ["Acme"]


def test_list_sort_by_score_puts_nulls_last(seeded):
    assert names(client.get("/jobs?sort=score")) == [
        "Acme",
        "Globex",
        "Hooli",
        "Initech",
    ]


def test_list_pagination(seeded):
    seen, cursor = [], None
    for _ in range(5):
        url = "/jobs?sort=score&limit=2" + (f"&cursor={cursor}" if cursor else "")
        body = client.get(url).json()
        seen += [i["company"] for i in body["items"]]
        cursor = body["next_cursor"]
        if cursor is None:
            break
    assert seen == ["Acme", "Globex", "Hooli", "Initech"]


def test_list_limit_and_cursor_validation(seeded):
    assert client.get("/jobs?limit=51").status_code == 422
    assert client.get("/jobs?limit=0").status_code == 422
    assert client.get("/jobs?cursor=!!!").status_code == 422
    assert client.get("/jobs?sort=bogus").status_code == 422
    assert client.get("/jobs?status=bogus").status_code == 422


def test_list_summary_shape(seeded):
    item = client.get("/jobs?q=Acme").json()["items"][0]
    assert set(item) == {
        "id", "company", "title", "location", "ctc_lpa_min", "ctc_lpa_max", "score",
        "musts_summary", "status", "red_flags", "created_at",
    }  # fmt: skip
    assert item["musts_summary"] == "1 of 2"
    assert (item["location"], item["ctc_lpa_min"], item["ctc_lpa_max"]) == (
        "Bengaluru, India",
        20,
        30,
    )


# --- GET /jobs/{id} -----------------------------------------------------------
def test_detail_shape(db_session):
    user = make_user(db_session)
    jd = JobDescription(company="Acme", must_have=["Python"])
    job = make_job(db_session, user, jd, company="Acme", score=70,
                   score_breakdown={"total": 70}, musts=[{"skill": "Python", "status": "have", "evidence_bullet_id": "b1"}])  # fmt: skip
    body = client.get(f"/jobs/{job.id}").json()
    assert set(body) == {"job", "jd", "score_breakdown", "musts", "latest_run"}
    assert body["jd"]["company"] == "Acme" and body["latest_run"] is None
    assert body["musts"][0] == {
        "skill": "Python",
        "status": "have",
        "evidence_bullet_id": "b1",
    }
    assert body["score_breakdown"] == {"total": 70}


def test_detail_without_extraction_has_null_jd(db_session):
    job = make_job(db_session, make_user(db_session), status="processing")
    assert client.get(f"/jobs/{job.id}").json()["jd"] is None


# --- PATCH --------------------------------------------------------------------
def test_patch_text_only_when_needs_paste_or_failed(db_session, queue):
    user = make_user(db_session)
    fresh = make_job(db_session, user, status="new")
    r = client.patch(f"/jobs/{fresh.id}", json={"text": "pasted"})
    assert r.status_code == 409 and r.json()["code"] == "invalid_state"

    for status in ("needs_paste", "failed"):
        job = make_job(db_session, user, status=status, raw_text=None, source="url")
        r = client.patch(f"/jobs/{job.id}", json={"text": "  the  pasted text "})
        assert r.status_code == 200
        assert r.json()["job"]["status"] == "processing"
        assert (
            "extract_jd",
            {"user_id": str(user.id), "job_id": job.id},
        ) in queue.calls
        db_session.refresh(job)
        assert job.raw_text == "the pasted text" and job.status_reason is None


def test_patch_archive_and_restore(db_session, queue):
    user = make_user(db_session)
    job = make_job(db_session, user, JobDescription())
    assert (
        client.patch(f"/jobs/{job.id}", json={"archived": True}).json()["job"]["status"]
        == "archived"
    )
    assert (
        client.patch(f"/jobs/{job.id}", json={"archived": False}).json()["job"][
            "status"
        ]
        == "new"
    )
    # archived before extraction ever finished: restoring re-runs extraction
    raw = make_job(db_session, user, status="archived")
    r = client.patch(f"/jobs/{raw.id}", json={"archived": False})
    assert r.json()["job"]["status"] == "processing"
    assert queue.names() == ["extract_jd"]


def test_patch_max_pages(db_session):
    job = make_job(db_session, make_user(db_session))
    assert (
        client.patch(f"/jobs/{job.id}", json={"max_pages_override": 2}).json()["job"][
            "max_pages_override"
        ]
        == 2
    )
    assert (
        client.patch(f"/jobs/{job.id}", json={"max_pages_override": None}).json()[
            "job"
        ]["max_pages_override"]
        is None
    )
    assert (
        client.patch(f"/jobs/{job.id}", json={"max_pages_override": 4}).status_code
        == 422
    )


@pytest.mark.parametrize(
    "body", [{}, {"archived": True, "max_pages_override": 1}, {"text": "x", "archived": True},
             {"text": "  "}, {"archived": None}, {"bogus": 1}],
)  # fmt: skip
def test_patch_requires_exactly_one_valid_field(db_session, body):
    job = make_job(db_session, make_user(db_session), status="needs_paste")
    assert client.patch(f"/jobs/{job.id}", json=body).status_code == 422


# --- isolation ------------------------------------------------------------------
def test_two_user_isolation_on_every_jobs_endpoint(db_session, queue):
    a = make_user(db_session, "auth0|A")
    approve_profile(db_session, a)
    job = make_job(db_session, a, JobDescription(company="Secret Co"), company="Secret Co",
                   status="needs_paste")  # fmt: skip
    img = client.post("/jobs/images", files={"file": ("s.png", PNG)}).json()["image_id"]
    client.post("/jobs", json={"source": "text", "text": "A private posting"})

    as_user("auth0|B")
    jid = job.id
    for method, path, body in [
        ("get", f"/jobs/{jid}", None),
        ("patch", f"/jobs/{jid}", {"text": "x"}),
        ("patch", f"/jobs/{jid}", {"archived": True}),
        ("patch", f"/jobs/{jid}", {"max_pages_override": 1}),
        ("post", f"/jobs/{jid}/tailor", {}),
    ]:
        r = client.request(method, path, json=body)
        assert r.status_code == 404, (method, path)
        assert "Secret" not in r.text
    assert client.get("/jobs").json()["items"] == []
    assert client.get("/jobs?q=secret").json()["items"] == []
    assert add(source="image", image_id=img).status_code == 404
    assert client.get("/events").json()["events"] == []
    db_session.refresh(job)
    assert job.status == "needs_paste"  # B's PATCH changed nothing


def test_events_endpoint_returns_only_own_and_paginates(db_session):
    from app.repositories.manager import RepositoryManager

    a, b = make_user(db_session, "auth0|A"), make_user(db_session, "auth0|B")
    repos = RepositoryManager(db_session)
    e1 = repos.jobs.add_event(a.id, "job_ready", {"job_id": "1"})
    repos.jobs.add_event(b.id, "job_ready", {"job_id": "other"})
    e3 = repos.jobs.add_event(a.id, "jobs_rescored", {"count": 2})
    body = client.get("/events").json()
    assert [e["id"] for e in body["events"]] == [e1.id, e3.id] and body[
        "last_id"
    ] == e3.id
    assert (
        client.get(f"/events?after={e1.id}").json()["events"][0]["type"]
        == "jobs_rescored"
    )
    assert client.get(f"/events?after={e3.id}").json() == {
        "events": [],
        "last_id": e3.id,
    }


def test_job_row_has_no_cross_user_leak_in_count(db_session):
    make_job(db_session, make_user(db_session, "auth0|A"))
    make_user(db_session, "auth0|B")
    as_user("auth0|B")
    assert db_session.query(Job).count() == 1
    assert client.get("/jobs").json() == {"items": [], "next_cursor": None}
