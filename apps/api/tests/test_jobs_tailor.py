import threading
from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker

from app import models  # noqa: F401
from app.core.config import settings
from app.core.security import token_claims
from app.db.base import Base
from app.main import app
from app.models.job import AgentRun
from app.repositories.job import QuotaExceeded, RunInProgress
from app.repositories.manager import RepositoryManager
from app.schemas.job import JobDescription
from app.schemas.profile import Bullet, Experience, ProfileData
from app.services.job import local_day
from tests.jobs_helpers import approve_profile, make_job, make_user

client = TestClient(app)


@pytest.fixture(autouse=True)
def auth():
    app.dependency_overrides[token_claims] = lambda: {"sub": "auth0|A"}


@pytest.fixture
def user(db_session):
    return make_user(db_session)


def tailor(job, **body):
    return client.post(f"/jobs/{job.id}/tailor", json=body)


def ready(db, user, **kw):
    return make_job(db, user, JobDescription(company="Acme"), company="Acme", **kw)


def test_other_users_job_is_404(db_session, user):
    job = ready(db_session, user)
    approve_profile(db_session, user)
    app.dependency_overrides[token_claims] = lambda: {"sub": "auth0|B"}
    r = tailor(job)
    assert r.status_code == 404 and r.json()["code"] == "not_found"
    assert db_session.query(AgentRun).count() == 0


@pytest.mark.parametrize("status", ["processing", "needs_paste", "failed"])
def test_jd_not_ready(db_session, user, status):
    approve_profile(db_session, user)
    r = tailor(make_job(db_session, user, status=status))
    assert r.status_code == 409 and r.json()["code"] == "jd_not_ready"


def test_red_flags_need_confirmation(db_session, user, queue):
    approve_profile(db_session, user)
    job = ready(db_session, user, red_flags=["registration fee"])
    r = tailor(job)
    assert r.status_code == 409 and r.json()["code"] == "red_flags"
    assert r.json()["details"] == {"red_flags": ["registration fee"]}
    assert db_session.query(AgentRun).count() == 0
    assert tailor(job, confirm_red_flags=False).status_code == 409
    assert tailor(job, confirm_red_flags=True).status_code == 202


def test_requires_an_approved_profile(db_session, user):
    r = tailor(ready(db_session, user))
    assert r.status_code == 409 and r.json()["code"] == "no_profile"


def test_profile_indexing_blocks(db_session, user):
    profile = approve_profile(db_session, user)
    profile.indexing_state = "indexing"
    db_session.commit()
    r = tailor(ready(db_session, user))
    assert r.status_code == 409 and r.json()["code"] == "profile_indexing"
    assert db_session.query(AgentRun).count() == 0


def test_success_creates_pinned_run_and_enqueues(db_session, user, queue):
    approve_profile(db_session, user)
    job = ready(db_session, user)
    r = tailor(job)
    assert r.status_code == 202
    run_id = r.json()["run_id"]
    run = db_session.get(AgentRun, run_id)
    assert (run.user_id, run.job_id, run.profile_version, run.status) == (
        user.id,
        job.id,
        1,
        "queued",
    )
    db_session.refresh(job)
    assert job.status == "tailoring"
    assert ("tailor", {"user_id": str(user.id), "run_id": run_id}) in queue.calls
    events = RepositoryManager(db_session).jobs.events_after(user.id, 0, 10)
    assert [(e.type, e.payload) for e in events][-1] == (
        "run_queued",
        {"job_id": job.id, "run_id": run_id},
    )
    assert client.get(f"/jobs/{job.id}").json()["latest_run"] == {
        "id": run_id,
        "status": "queued",
    }


def test_body_is_optional(db_session, user):
    approve_profile(db_session, user)
    job = ready(db_session, user)
    assert client.post(f"/jobs/{job.id}/tailor").status_code == 202


def test_run_in_progress_returns_existing_run_id(db_session, user):
    approve_profile(db_session, user)
    job = ready(db_session, user)
    first = tailor(job).json()["run_id"]
    r = tailor(job)
    assert r.status_code == 409 and r.json()["code"] == "run_in_progress"
    assert r.json()["details"] == {"run_id": first}
    assert db_session.query(AgentRun).count() == 1


def test_run_pins_the_version_it_started_with(db_session, user):
    approve_profile(db_session, user)  # v1
    job1, job2 = ready(db_session, user), ready(db_session, user)
    run1 = tailor(job1).json()["run_id"]

    v2 = ProfileData(
        experience=[
            Experience(
                id="x", company="New", bullets=[Bullet(id="n1", text="New work")]
            )
        ]
    )
    approve_profile(db_session, user, v2)  # v2 approved while run1 is in flight
    assert client.get("/profile").json()["version"] == 2

    assert db_session.get(AgentRun, run1).profile_version == 1  # unchanged
    run2 = tailor(job2).json()["run_id"]
    assert db_session.get(AgentRun, run2).profile_version == 2


def test_daily_cap(db_session, user, monkeypatch):
    monkeypatch.setattr(settings, "daily_run_cap", 2)
    approve_profile(db_session, user)
    jobs = [ready(db_session, user) for _ in range(3)]
    assert tailor(jobs[0]).status_code == 202
    assert tailor(jobs[1]).status_code == 202
    r = tailor(jobs[2])
    assert r.status_code == 429 and r.json()["code"] == "daily_cap"
    assert r.json()["details"] == {"used": 2, "cap": 2}
    db_session.refresh(jobs[2])
    assert jobs[2].status == "new"  # a refused request changes nothing
    # the cap is per user
    other = make_user(db_session, "auth0|B")
    approve_profile(db_session, other)
    app.dependency_overrides[token_claims] = lambda: {"sub": "auth0|B"}
    assert tailor(ready(db_session, other)).status_code == 202


def test_refused_requests_do_not_consume_quota(db_session, user, monkeypatch):
    monkeypatch.setattr(settings, "daily_run_cap", 2)
    approve_profile(db_session, user)
    job = ready(db_session, user, red_flags=["x"])
    for _ in range(5):
        assert tailor(job).status_code == 409  # red_flags, never reaches the counter
    assert tailor(job, confirm_red_flags=True).status_code == 202
    assert RepositoryManager(db_session).jobs.quota_used(user.id, local_day()) == 1


def test_day_resets_at_midnight_ist():
    assert (
        local_day(datetime(2026, 11, 4, 18, 29, tzinfo=UTC)) == "2026-11-04"
    )  # 23:59 IST
    assert (
        local_day(datetime(2026, 11, 4, 18, 30, tzinfo=UTC)) == "2026-11-05"
    )  # 00:00 IST


def test_quota_row_is_per_day(db_session, user):
    approve_profile(db_session, user)
    repos = RepositoryManager(db_session)
    job = ready(db_session, user)
    repos.jobs.reserve_run(user.id, job, 1, "2026-01-01", 1)
    job2 = ready(db_session, user)
    repos.jobs.reserve_run(
        user.id, job2, 1, "2026-01-02", 1
    )  # new day, fresh allowance
    with pytest.raises(QuotaExceeded):
        repos.jobs.reserve_run(user.id, ready(db_session, user), 1, "2026-01-02", 1)


# --- concurrency: real threads, separate sessions, one on-disk database ----------------
@pytest.fixture
def shared_db(tmp_path):
    engine = create_engine(
        f"sqlite:///{tmp_path / 'c.db'}",
        connect_args={"check_same_thread": False, "timeout": 30},
    )

    @event.listens_for(engine, "connect")
    def _no_autobegin(dbapi, _):
        dbapi.isolation_level = None  # we emit BEGIN ourselves

    @event.listens_for(engine, "begin")
    def _begin(conn):
        conn.exec_driver_sql("BEGIN IMMEDIATE")  # writers queue instead of erroring

    Base.metadata.create_all(engine)
    return sessionmaker(engine, expire_on_commit=False)


def race(factory, n, work):
    results, barrier = [], threading.Barrier(n)

    def target(i):
        with factory() as session:
            barrier.wait()
            try:
                results.append(("ok", work(RepositoryManager(session), i)))
            except Exception as e:  # noqa: BLE001
                results.append(("err", e))

    threads = [threading.Thread(target=target, args=(i,)) for i in range(n)]
    [t.start() for t in threads]
    [t.join() for t in threads]
    return results


def test_concurrent_requests_at_the_cap_boundary(shared_db):
    with shared_db() as s:
        user = make_user(s)
        job_ids = [make_job(s, user).id for _ in range(8)]
        uid = user.id

    def work(repos, i):
        job = repos.jobs.get_for_user(uid, job_ids[i])
        return repos.jobs.reserve_run(uid, job, 1, "2026-01-01", 3).id

    results = race(shared_db, 8, work)
    assert sum(r[0] == "ok" for r in results) == 3
    assert all(isinstance(r[1], QuotaExceeded) for r in results if r[0] == "err")
    with shared_db() as s:
        assert RepositoryManager(s).jobs.quota_used(uid, "2026-01-01") == 3
        assert s.query(AgentRun).count() == 3


def test_concurrent_requests_for_the_same_job_start_one_run(shared_db):
    with shared_db() as s:
        user = make_user(s)
        job_id = make_job(s, user).id
        uid = user.id

    def work(repos, i):
        job = repos.jobs.get_for_user(uid, job_id)
        return repos.jobs.reserve_run(uid, job, 1, "2026-01-01", 10).id

    results = race(shared_db, 6, work)
    assert sum(r[0] == "ok" for r in results) == 1
    assert all(isinstance(r[1], RunInProgress) for r in results if r[0] == "err")
    with shared_db() as s:
        assert s.query(AgentRun).count() == 1
        # losers gave their slot back: only the one real run counts against the cap
        assert RepositoryManager(s).jobs.quota_used(uid, "2026-01-01") == 1
