from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo

import pytest
from fastapi.testclient import TestClient

from app.core.config import settings
from app.core.security import token_claims
from app.main import app
from app.models.user import User
from app.repositories.manager import RepositoryManager
from app.schemas.job import JobDescription
from app.tasks import jobs as job_tasks
from tests.jobs_helpers import Boom, approve_profile, make_ctx, make_job, make_user
from tests.runs_helpers import run_ready

client = TestClient(app)

VALID = {
    "target_roles": ["Backend Engineer", "Platform Engineer"],
    "cities": ["Bengaluru", "Remote"],
    "current_ctc_lpa": 18.5,
    "expected_ctc_lpa": 30,
    "notice_days": 60,
    "default_length": "auto",
    "template": "classic",
    "daily_cap": 5,
    "coverage_target": 0.7,
    "theme": "dark",
}


@pytest.fixture(autouse=True)
def auth():
    app.dependency_overrides[token_claims] = lambda: {"sub": "auth0|A"}


@pytest.fixture
def user(db_session):
    return make_user(db_session)


def put(body=None, **kw):
    return client.put(
        "/settings", json=VALID | (body or {}) | kw.pop("extra", {}), **kw
    )


def test_defaults_for_a_new_user(user):
    r = client.get("/settings")
    assert r.status_code == 200 and r.headers["etag"] == '"0"'
    body = r.json()
    assert body["configured"] is False and body["rev"] == 0
    assert body["preferences"]["daily_cap"] == settings.daily_run_cap
    assert (
        body["preferences"]["default_length"] == "auto" and body["runs_used_today"] == 0
    )
    resets = datetime.fromisoformat(body["cap_resets_at"]).astimezone(
        ZoneInfo("Asia/Kolkata")
    )
    assert (resets.hour, resets.minute, resets.second) == (0, 0, 0)
    assert datetime.now(UTC) < resets <= datetime.now(UTC) + timedelta(hours=24)


def test_put_replaces_and_get_returns_it(user):
    r = put()
    assert r.status_code == 200, r.text
    assert (
        r.json()["configured"] is True
        and r.json()["rev"] == 1
        and r.headers["etag"] == '"1"'
    )
    assert client.get("/settings").json()["preferences"] == VALID
    smaller = {**VALID, "target_roles": ["SRE"], "theme": "light"}
    assert client.put("/settings", json=smaller).status_code == 200
    assert client.get("/settings").json()["preferences"] == smaller  # full replace


@pytest.mark.parametrize(
    "field,value",
    [
        ("target_roles", []),
        ("target_roles", [f"r{i}" for i in range(11)]),
        ("target_roles", ["  "]),
        ("target_roles", ["x" * 81]),
        ("cities", ["Atlantis"]),
        ("cities", ["Remote"] * 31),
        ("current_ctc_lpa", -0.1),
        ("current_ctc_lpa", 500.1),
        ("expected_ctc_lpa", 501),
        ("expected_ctc_lpa", "lots"),
        ("notice_days", -1),
        ("notice_days", 181),
        ("notice_days", 1.5),
        ("default_length", 4),
        ("default_length", "auto "),
        ("template", "fancy"),
        ("daily_cap", 0),
        ("daily_cap", 51),
        ("coverage_target", 0.55),
        ("coverage_target", 0.9),
        ("theme", "sepia"),
    ],
)
def test_validation_bounds(user, field, value):
    r = put({field: value})
    assert r.status_code == 422 and r.json()["code"] == "validation_error"
    assert client.get("/settings").json()["configured"] is False  # nothing saved


@pytest.mark.parametrize(
    "field,value",
    [
        ("target_roles", ["a"]),
        ("target_roles", [f"r{i}" for i in range(10)]),
        ("current_ctc_lpa", 0),
        ("expected_ctc_lpa", 500),
        ("notice_days", 0),
        ("notice_days", 180),
        ("default_length", 1),
        ("default_length", 3),
        ("template", "compact"),
        ("daily_cap", 1),
        ("daily_cap", 50),
        ("coverage_target", 0.5),
        ("theme", "system"),
        ("cities", []),
    ],
)
def test_bounds_are_inclusive(user, field, value):
    assert put({field: value}).status_code == 200


def test_unknown_and_missing_fields_are_rejected(user):
    assert put(extra={"favourite_colour": "red"}).status_code == 422
    partial = {k: v for k, v in VALID.items() if k != "theme"}
    assert client.put("/settings", json=partial).status_code == 422


def test_daily_cap_ceiling_comes_from_config(user, monkeypatch):
    monkeypatch.setattr(settings, "daily_cap_max", 20)
    assert put({"daily_cap": 21}).status_code == 422
    assert put({"daily_cap": 20}).status_code == 200
    assert client.get("/settings").json()["daily_cap"] == 20


def test_cities_are_matched_case_insensitively_and_deduplicated(user):
    assert put({"cities": ["bengaluru", "REMOTE", "Bengaluru"]}).status_code == 200
    assert client.get("/settings").json()["preferences"]["cities"] == [
        "Bengaluru",
        "Remote",
    ]


def test_stale_write_is_409(user):
    assert put(headers={"If-Match": '"0"'}).status_code == 200
    r = put({"theme": "light"}, headers={"If-Match": '"0"'})
    assert r.status_code == 409 and r.json()["code"] == "stale_write"
    assert r.json()["details"] == {"rev": 1}
    assert client.get("/settings").json()["preferences"]["theme"] == "dark"
    assert put({"theme": "light"}, headers={"If-Match": '"1"'}).status_code == 200


# --- rescoring ---------------------------------------------------------------
@pytest.mark.parametrize(
    "change,expect",
    [
        ({"cities": ["Pune"]}, True),
        ({"expected_ctc_lpa": 31}, True),
        ({"target_roles": ["Data Engineer"]}, True),
        ({"theme": "light"}, False),
        ({"daily_cap": 9}, False),
        ({"notice_days": 10}, False),
        ({}, False),
    ],
)
def test_only_scoring_inputs_trigger_a_rescore(user, queue, change, expect):
    put()
    queue.calls.clear()
    assert put(change).status_code == 200
    assert (("rescore_jobs", {"user_id": str(user.id)}) in queue.calls) is expect


def test_first_save_that_differs_from_defaults_rescores(user, queue):
    put()
    assert queue.names() == ["rescore_jobs"]


def test_rescore_uses_the_saved_preferences_and_makes_no_llm_calls(
    db_session, tmp_path, user
):
    approve_profile(db_session, user)
    jd = JobDescription(company="X", title="Eng", ctc_lpa_max=20, work_mode="remote")
    job = make_job(db_session, user, jd, company="X", score=1)
    ctx = make_ctx(
        db_session,
        tmp_path,
        extractor=Boom(),
        transcriber=Boom(),
        fetcher=Boom(),
    )

    def score_with(expected):
        row = db_session.get(User, user.id)
        row.preferences = {**VALID, "expected_ctc_lpa": expected, "cities": ["Remote"]}
        db_session.commit()
        job_tasks.rescore_jobs(ctx, user.id)
        db_session.refresh(job)
        return job.score

    assert score_with(10) > score_with(
        50
    )  # expecting far above the offer lowers the match


# --- cap ---------------------------------------------------------------------
def test_daily_cap_applies_from_the_next_run(db_session, tmp_path, user):
    assert put({"daily_cap": 1}).status_code == 200
    run_ready(db_session, tmp_path, user, status="in_review")  # uses the one slot
    assert client.get("/settings").json()["runs_used_today"] == 1
    approve_profile(db_session, user)
    job = make_job(db_session, user, JobDescription(company="Y"), company="Y")
    r = client.post(f"/jobs/{job.id}/tailor")
    assert r.status_code == 429 and r.json()["details"] == {"used": 1, "cap": 1}
    assert put({"daily_cap": 2}).status_code == 200
    assert client.post(f"/jobs/{job.id}/tailor").status_code == 202


def test_default_length_sets_the_runs_page_limit(db_session, user):
    assert put({"default_length": 2}).status_code == 200
    approve_profile(db_session, user)
    job = make_job(db_session, user, JobDescription(company="Y"), company="Y")
    run_id = client.post(f"/jobs/{job.id}/tailor").json()["run_id"]
    assert (
        RepositoryManager(db_session).runs.get_for_user(user.id, run_id).max_pages == 2
    )


def test_settings_are_per_user(db_session, user):
    put()
    make_user(db_session, "auth0|B")
    app.dependency_overrides[token_claims] = lambda: {"sub": "auth0|B"}
    body = client.get("/settings").json()
    assert body["configured"] is False and body["preferences"]["target_roles"] == []
