"""Caps are atomic conditional updates (like RunQuota): tested with real threads."""

import contextlib

from sqlalchemy import select

from app.apply.runner import ApplyContext, run_application
from app.apply.worker import poll_once
from app.core.config import settings
from app.models.application import Application
from app.repositories.application import CapReached, Caps
from app.repositories.manager import RepositoryManager
from tests.jobs_helpers import make_job, make_user
from tests.test_jobs_tailor import race, shared_db  # noqa: F401  (fixture + helper)

DAY, HOUR = "2026-11-19", "2026-11-19T10"


def mk(session, user, *, site="greenhouse", ats="greenhouse", status="running"):
    job = make_job(session, user)
    app = Application(
        user_id=user.id, job_id=job.id, run_id="r", channel="playwright", ats=ats,
        site=site, status=status, apply_url="https://boards.greenhouse.io/a",
    )  # fmt: skip
    session.add(app)
    session.commit()
    return app.id


def reserve(factory, uid, ids, caps, n):
    def work(repos, i):
        app = repos.applications.get_for_user(uid, ids[i])
        repos.applications.reserve(app, day=DAY, hour=HOUR, caps=caps)
        return app.id

    return race(factory, n, work)


def test_user_day_cap_holds_under_concurrency(shared_db):  # noqa: F811
    with shared_db() as s:
        user = make_user(s)
        ids = [mk(s, user) for _ in range(8)]
        uid = user.id
    results = reserve(shared_db, uid, ids, Caps(3, 99, None), 8)
    assert sum(r[0] == "ok" for r in results) == 3
    assert all(
        isinstance(r[1], CapReached) and r[1].scope == "user_day"
        for r in results
        if r[0] == "err"
    )
    with shared_db() as s:
        repos = RepositoryManager(s)
        assert repos.applications.used(uid, DAY, "*") == 3
        assert repos.applications.used(uid, DAY, "greenhouse") == 3


def test_site_cap_holds_under_concurrency_and_a_failed_site_slot_returns_the_user_slot(
    shared_db,  # noqa: F811
):
    with shared_db() as s:
        user = make_user(s)
        ids = [mk(s, user, site="wellfound", ats=None) for _ in range(6)]
        uid = user.id
    results = reserve(shared_db, uid, ids, Caps(50, 2, None), 6)
    assert sum(r[0] == "ok" for r in results) == 2
    assert {r[1].scope for r in results if r[0] == "err"} == {"site_day"}
    with shared_db() as s:  # rolled back: the user total did not leak slots
        assert RepositoryManager(s).applications.used(uid, DAY, "*") == 2


def test_ats_hourly_cap_is_global_across_users(shared_db):  # noqa: F811
    with shared_db() as s:
        users = [make_user(s, f"auth0|{i}") for i in range(4)]
        pairs = [(u.id, mk(s, u)) for u in users for _ in range(2)]

    def work(repos, i):
        uid, aid = pairs[i]
        repos.applications.reserve(
            repos.applications.get_for_user(uid, aid),
            day=DAY,
            hour=HOUR,
            caps=Caps(50, 50, 5),
        )

    results = race(shared_db, 8, work)
    assert sum(r[0] == "ok" for r in results) == 5
    assert {r[1].scope for r in results if r[0] == "err"} == {"ats_hour"}
    with shared_db() as s:
        assert RepositoryManager(s).applications.ats_used("greenhouse", HOUR) == 5
        total = sum(
            RepositoryManager(s).applications.used(u.id, DAY, "*") for u in users
        )
        assert total == 5


def test_reserve_is_idempotent_and_release_returns_the_slot(db_session):
    user = make_user(db_session)
    repos = RepositoryManager(db_session)
    aid = mk(db_session, user)
    app = repos.applications.get_for_user(user.id, aid)
    caps = Caps(1, 1, 1)
    repos.applications.reserve(app, day=DAY, hour=HOUR, caps=caps)
    repos.applications.reserve(app, day=DAY, hour=HOUR, caps=caps)  # no second slot
    assert repos.applications.used(user.id, DAY, "*") == 1
    other = repos.applications.get_for_user(user.id, mk(db_session, user))
    try:
        repos.applications.reserve(other, day=DAY, hour=HOUR, caps=caps)
        raise AssertionError("cap not enforced")
    except CapReached:
        pass
    repos.applications.stage_release(app)
    db_session.commit()
    assert repos.applications.used(user.id, DAY, "*") == 0
    assert repos.applications.ats_used("greenhouse", HOUR) == 0
    repos.applications.reserve(other, day=DAY, hour=HOUR, caps=caps)  # room again


def test_site_caps_default_to_five_for_wellfound_and_naukri():
    assert settings.autopilot_site_caps["wellfound"] == 5
    assert settings.autopilot_site_caps["naukri"] == 5


def test_worker_does_not_start_applications_over_the_cap(db_session, tmp_path):
    user = make_user(db_session)
    repos = RepositoryManager(db_session)
    from app.core.clock import local_day
    from app.services.application import hour_key

    user.autopilot = {"daily_apply_cap": 1}
    db_session.commit()
    first = repos.applications.get_for_user(user.id, mk(db_session, user))
    repos.applications.reserve(
        first, day=local_day(), hour=hour_key(), caps=Caps(1, 9, 9)
    )
    queued = mk(db_session, user, status="queued")

    class NoBrowser:
        def session(self, policy):
            raise AssertionError("must not open a browser over the cap")

    ctx = ApplyContext(
        session_factory=lambda: contextlib.nullcontext(db_session),
        storage=None, driver=NoBrowser(),
    )  # fmt: skip
    assert poll_once(ctx) == 0
    assert (
        db_session.scalar(select(Application.status).where(Application.id == queued))
        == "queued"
    )
    # and run_application itself defers instead of failing when the slot is gone
    assert run_application(ctx, user.id, queued) == "queued"
