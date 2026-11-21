"""Real Chrome (channel="chrome") against local mock ATS pages on 127.0.0.1.
Skipped when Chrome is unavailable. Never touches the internet; never submits anywhere
real."""

import pytest
from sqlalchemy import select

from app.apply.fallback import FallbackPlan, Proposal
from app.apply.runner import run_application
from app.core.config import settings
from app.models.application import Application
from app.models.job import Event
from app.models.tracker import TrackerCard
from app.repositories.manager import RepositoryManager
from app.services.application import ApplicationService
from tests.apply_helpers import (
    approved_run,
    enable_apply,
    make_apply_ctx,
    needs_chrome,
)
from tests.jobs_helpers import make_user

pytestmark = needs_chrome

PREFS = {"notice_days": 30}


@pytest.fixture(autouse=True)
def _apply(monkeypatch):
    enable_apply(monkeypatch)


def setup(db, tmp_path, ats_server, path, *, mode="manual", prefs=PREFS, sub="auth0|A"):
    user = make_user(db, sub)
    job, run = approved_run(db, tmp_path, user, ats_server.base + path, prefs=prefs)
    svc = ApplicationService(
        RepositoryManager(db), None, make_apply_ctx(db, tmp_path).storage
    )
    app = svc.create_for_run(user.id, run.id, mode=mode)
    return user, job, run, app


def go(db, tmp_path, user, app, **over):
    ctx = make_apply_ctx(db, tmp_path, **over)
    run_application(ctx, user.id, app.id)
    db.refresh(app)
    return ctx


# --- fill, submit, confirm on each ATS style ---------------------------------------
def test_greenhouse_style_form_is_filled_submitted_and_confirmed(
    db_session, tmp_path, ats
):
    user, _job, run, app = setup(db_session, tmp_path, ats, "/greenhouse/jobs/1")
    ctx = go(db_session, tmp_path, user, app)
    assert app.status == "submitted", app.skip_reason
    sub = ats.submissions[0]
    assert (
        sub["fields"]["first_name"] == "Ada"
        and sub["fields"]["last_name"] == "Lovelace"
    )
    assert sub["fields"]["email"] == "ada@example.com"
    assert sub["fields"]["notice"] == "30 days"  # from settings via answer_for
    assert sub["fields"]["linkedin"] == "https://www.linkedin.com/in/ada"
    # the file is the approved PDF (named after the approval)
    approval = RepositoryManager(db_session).runs.approval_for(user.id, run.id)
    assert sub["files"]["resume"][0] == approval.file_name
    assert sub["files"]["resume"][1] == len(ctx.storage.read(approval.pdf_key))
    assert ats.requests[0] == "/greenhouse/jobs/1"


def test_proof_answers_tracker_and_event_after_submit(db_session, tmp_path, ats):
    user, job, _run, app = setup(db_session, tmp_path, ats, "/greenhouse/jobs/1")
    ctx = go(db_session, tmp_path, user, app)
    assert app.status == "submitted" and app.submitted_at is not None
    prefix = f"users/{user.id.hex}/applications/{app.id}/"
    assert [k for k in app.screenshot_keys] == [
        prefix + "filled.png",
        prefix + "confirmation.png",
    ]
    assert all(ctx.storage.read(k).startswith(b"\x89PNG") for k in app.screenshot_keys)
    labels = {a["label"]: a for a in app.answers_used}
    assert labels["First Name"]["source"] == "profile"
    assert labels["What is your notice period?"]["source"] == "settings"
    assert labels["Resume/CV"]["source"] == "approved_pdf"
    card = db_session.scalar(select(TrackerCard).where(TrackerCard.job_id == job.id))
    assert card.column == "applied" and card.applied_at is not None
    ev = db_session.scalars(select(Event).where(Event.type == "job_applied")).all()
    assert ev and ev[0].payload["job_id"] == job.id


def test_lever_style_form(db_session, tmp_path, ats):
    user, *_, app = setup(db_session, tmp_path, ats, "/lever/co/1/apply")
    go(db_session, tmp_path, user, app)
    assert app.status == "submitted", app.skip_reason
    f = ats.submissions[0]["fields"]
    assert f["name"] == "Ada Lovelace" and f["urls[LinkedIn]"].endswith("/in/ada")
    assert (
        "comments" not in f or f["comments"] == ""
    )  # optional open field never invented
    assert app.ats == "lever"


def test_ashby_style_client_rendered_form(db_session, tmp_path, ats):
    user, *_, app = setup(db_session, tmp_path, ats, "/ashby/co/1/application")
    go(db_session, tmp_path, user, app)
    assert app.status == "submitted", app.skip_reason
    assert ats.submissions[0]["fields"]["_systemfield_name"] == "Ada Lovelace"
    assert ats.submissions[0]["files"]["_systemfield_resume"][0].endswith(".pdf")


def test_himalayas_application_link_is_opened_first_then_adapter_detected(
    db_session, tmp_path, ats
):
    user, *_, app = setup(db_session, tmp_path, ats, "/himalayas/apply/42")
    assert app.ats == "unknown"
    go(db_session, tmp_path, user, app)
    assert ats.requests[0] == "/himalayas/apply/42"  # the applicationLink first
    assert "/greenhouse/jobs/1" in ats.requests  # then the employer form
    assert app.status == "submitted" and app.ats == "greenhouse"


def test_pacing_pauses_between_actions(db_session, tmp_path, ats):
    user, *_, app = setup(db_session, tmp_path, ats, "/greenhouse/jobs/1")
    ctx = go(db_session, tmp_path, user, app)
    lo, hi = settings.autopilot_pacing_ms
    assert len(ctx.paces) >= 6 and all(lo <= p <= hi for p in ctx.paces)


# --- blockers: never submit, never bypass ---------------------------------------------
@pytest.mark.parametrize(
    ("path", "reason"),
    [
        ("/captcha", "captcha"),
        ("/login", "login"),
        ("/verify", "verification"),
        ("/botcheck", "bot_check"),
        ("/noform", "unsupported_form"),
    ],
)
def test_autopilot_blockers_skip_with_reason_and_link_and_never_submit(
    db_session, tmp_path, ats, path, reason
):
    user, *_, app = setup(db_session, tmp_path, ats, path, mode="autopilot")
    go(db_session, tmp_path, user, app)
    assert app.status == "skipped" and app.skip_reason == reason
    assert app.apply_url == ats.base + path  # the direct link for a person
    assert ats.submissions == []
    assert not app.slot_held  # nothing counted


@pytest.mark.parametrize("path", ["/captcha", "/login", "/verify", "/botcheck"])
def test_manual_mode_blockers_are_also_never_submitted(db_session, tmp_path, ats, path):
    user, *_, app = setup(db_session, tmp_path, ats, path, mode="manual")
    go(db_session, tmp_path, user, app)
    assert app.status == "skipped" and ats.submissions == []


def test_layout_change_page_with_no_fields_is_a_blocker(db_session, tmp_path, ats):
    ats.pages["/gh/empty"] = (
        '<html><body><form id="application_form"></form></body></html>'
    )
    user, *_, app = setup(db_session, tmp_path, ats, "/gh/empty", mode="autopilot")
    go(db_session, tmp_path, user, app)
    assert app.status == "skipped" and app.skip_reason == "layout_change"
    assert ats.submissions == []


@pytest.mark.parametrize("path", ["/gh/open-question", "/gh/work-auth", "/gh/consent"])
def test_required_field_without_a_value_skips_in_autopilot(
    db_session, tmp_path, ats, path
):
    user, *_, app = setup(db_session, tmp_path, ats, path, mode="autopilot")
    go(db_session, tmp_path, user, app)
    assert app.status == "skipped" and app.skip_reason == "required_field_no_value"
    assert ats.submissions == []


def test_manual_mode_waits_for_the_unmapped_field_and_answer_resumes(
    db_session, tmp_path, ats
):
    user, *_, app = setup(db_session, tmp_path, ats, "/gh/work-auth", mode="manual")
    go(db_session, tmp_path, user, app)
    assert app.status == "waiting_for_user" and ats.submissions == []
    assert not app.slot_held
    pending = app.pending_fields
    assert pending[0]["key"] == "wa" and "authorized" in pending[0]["label"]
    svc = ApplicationService(
        RepositoryManager(db_session),
        None,
        make_apply_ctx(db_session, tmp_path).storage,
    )
    from app.schemas.application import ApplicationAnswerIn, FieldAnswer

    svc.answer(
        user.id,
        app.id,
        ApplicationAnswerIn(answers=[FieldAnswer(key="wa", value="Yes")]),
    )
    assert app.status == "queued"
    go(db_session, tmp_path, user, app)
    assert app.status == "submitted", app.skip_reason
    assert ats.submissions[0]["fields"]["wa"] == "y"
    used = {a["label"]: a["source"] for a in app.answers_used}
    assert used["Are you legally authorized to work in India?"] == "user"


# --- network policy ---------------------------------------------------------------------
def test_requests_to_other_hosts_are_blocked(db_session, tmp_path, ats):
    from tests.apply_helpers import MockAts

    spy = MockAts().start()
    spy.pages["/pixel"] = "x"
    try:
        port = spy.httpd.server_port
        ats.pages["/gh/tracker"] = ats.pages["/greenhouse/jobs/1"].replace(
            "<h1>", f'<img src="http://localhost:{port}/pixel"><h1>'
        )
        user, *_, app = setup(
            db_session, tmp_path, ats, "/gh/tracker", mode="autopilot"
        )
        go(db_session, tmp_path, user, app)
        assert app.status == "submitted"
        assert spy.requests == []  # route-blocked: it never left the browser
    finally:
        spy.stop()


def test_redirect_to_a_foreign_host_is_refused(db_session, tmp_path, ats):
    from tests.apply_helpers import MockAts

    spy = MockAts().start()
    ats.redirects["/away"] = f"http://localhost:{spy.httpd.server_port}/x"
    try:
        user, *_, app = setup(db_session, tmp_path, ats, "/away", mode="autopilot")
        go(db_session, tmp_path, user, app)
        assert app.status == "skipped" and app.skip_reason == "host_not_allowed"
        assert spy.requests == []
    finally:
        spy.stop()


# --- unknown form fallback ---------------------------------------------------------------
class FakeFallback:
    def __init__(self, proposals=(), intended=None):
        self.proposals, self.intended, self.calls = list(proposals), intended, 0

    def propose(self, fields, plan):
        self.calls += 1
        keys = [f.key for f in fields] if self.intended is None else self.intended
        return FallbackPlan(intended=keys, proposals=list(self.proposals))


@pytest.fixture
def generic_on(monkeypatch):
    monkeypatch.setattr(
        settings, "apply_enabled_ats", ["greenhouse", "lever", "ashby", "generic"]
    )


def test_unknown_form_fully_mapped_submits_without_needing_the_fallback(
    db_session, tmp_path, ats, generic_on
):
    user, *_, app = setup(db_session, tmp_path, ats, "/generic/form", mode="autopilot")
    fb = FakeFallback()
    go(db_session, tmp_path, user, app, fallback=fb)
    assert app.status == "submitted", app.skip_reason
    assert fb.calls == 0


def test_unknown_form_unmappable_required_field_skips(
    db_session, tmp_path, ats, generic_on
):
    user, *_, app = setup(
        db_session, tmp_path, ats, "/generic/quirky", mode="autopilot"
    )
    go(db_session, tmp_path, user, app)  # ConservativeFallback by default
    assert app.status == "skipped" and app.skip_reason == "required_field_no_value"
    assert ats.submissions == []


def test_fallback_must_list_every_field_and_be_confident(
    db_session, tmp_path, ats, generic_on
):
    user, *_, app = setup(
        db_session, tmp_path, ats, "/generic/quirky", mode="autopilot"
    )
    go(db_session, tmp_path, user, app, fallback=FakeFallback(intended=["n"]))
    assert app.skip_reason == "fallback_incomplete" and ats.submissions == []

    user2, *_, app2 = setup(
        db_session, tmp_path, ats, "/generic/quirky", mode="autopilot", sub="auth0|B"
    )
    low = FakeFallback([Proposal("q", "Blue", "profile", 0.5)])
    go(db_session, tmp_path, user2, app2, fallback=low)
    assert app2.skip_reason == "required_field_no_value" and ats.submissions == []

    user3, *_, app3 = setup(
        db_session, tmp_path, ats, "/generic/quirky", mode="autopilot", sub="auth0|C"
    )
    bad_source = FakeFallback([Proposal("q", "Blue", "invented", 0.99)])
    go(db_session, tmp_path, user3, app3, fallback=bad_source)
    assert app3.skip_reason == "required_field_no_value" and ats.submissions == []


def test_fallback_with_confident_allowed_source_is_used(
    db_session, tmp_path, ats, generic_on
):
    user, *_, app = setup(
        db_session, tmp_path, ats, "/generic/quirky", mode="autopilot"
    )
    go(
        db_session,
        tmp_path,
        user,
        app,
        fallback=FakeFallback([Proposal("q", "Blue", "profile", 0.95)]),
    )
    assert app.status == "submitted" and ats.submissions[0]["fields"]["q"] == "Blue"


def test_generic_adapter_is_off_unless_enabled(db_session, tmp_path, ats):
    user, *_, app = setup(db_session, tmp_path, ats, "/generic/form", mode="autopilot")
    go(db_session, tmp_path, user, app)
    assert app.status == "skipped" and app.skip_reason == "ats_disabled"
    assert ats.submissions == []


# --- kill switches, pause, unconfirmed ---------------------------------------------------
def test_global_kill_switch_and_ats_switch(db_session, tmp_path, ats, monkeypatch):
    user, *_, app = setup(
        db_session, tmp_path, ats, "/greenhouse/jobs/1", mode="autopilot"
    )
    monkeypatch.setattr(settings, "apply_enabled", False)
    go(db_session, tmp_path, user, app)
    assert (
        app.status == "skipped"
        and app.skip_reason == "kill_switch"
        and ats.requests == []
    )

    monkeypatch.setattr(settings, "apply_enabled", True)
    monkeypatch.setattr(settings, "apply_enabled_ats", ["lever"])
    user2, *_, app2 = setup(
        db_session, tmp_path, ats, "/greenhouse/jobs/1", mode="autopilot", sub="auth0|B"
    )
    go(db_session, tmp_path, user2, app2)  # detected greenhouse is switched off
    assert app2.skip_reason == "ats_disabled" and ats.submissions == []


def test_site_auto_pauses_after_two_consecutive_blocks_and_resets_on_submit(
    db_session, tmp_path, ats
):
    user = make_user(db_session)
    repos = RepositoryManager(db_session)
    apps = []
    for i in range(3):
        _job, run = approved_run(
            db_session, tmp_path, user, ats.base + "/captcha", prefs=PREFS
        )
        svc = ApplicationService(
            repos, None, make_apply_ctx(db_session, tmp_path).storage
        )
        apps.append(svc.create_for_run(user.id, run.id, mode="autopilot"))
    go(db_session, tmp_path, user, apps[0])
    assert repos.applications.paused_sites(user.id) == []
    go(db_session, tmp_path, user, apps[1])
    assert repos.applications.paused_sites(user.id) == [
        "unknown"
    ] or repos.applications.paused_sites(user.id)
    site = apps[1].site
    assert site in repos.applications.paused_sites(user.id)
    go(db_session, tmp_path, user, apps[2])  # paused: not even opened
    n_requests = len(ats.requests)
    assert apps[2].skip_reason in ("site_paused", "captcha")
    go(db_session, tmp_path, user, apps[2])
    assert len(ats.requests) == n_requests


def test_unconfirmed_submit_is_failed_not_submitted_and_not_counted(
    db_session, tmp_path, ats, monkeypatch
):
    monkeypatch.setattr(settings, "apply_nav_timeout_ms", 1500)
    ats.confirm = False
    user, *_, app = setup(db_session, tmp_path, ats, "/greenhouse/jobs/1")
    go(db_session, tmp_path, user, app)
    assert app.status == "failed" and app.error == "unconfirmed_submit"
    assert not app.slot_held


def test_cancelled_application_is_not_run(db_session, tmp_path, ats):
    user, *_, app = setup(db_session, tmp_path, ats, "/greenhouse/jobs/1")
    ApplicationService(
        RepositoryManager(db_session),
        None,
        make_apply_ctx(db_session, tmp_path).storage,
    ).cancel(user.id, app.id)
    go(db_session, tmp_path, user, app)
    assert app.status == "cancelled" and ats.requests == []
    assert db_session.scalar(select(Application.attempts)) == 0


def test_apply_logs_carry_no_personal_data(db_session, tmp_path, ats, caplog):
    import logging

    caplog.set_level(logging.DEBUG, logger="app")
    user, *_, app = setup(db_session, tmp_path, ats, "/gh/work-auth", mode="manual")
    go(db_session, tmp_path, user, app)
    text = "\n".join(r.getMessage() for r in caplog.records)
    for secret in (
        "Ada",
        "Lovelace",
        "ada@example.com",
        "90000",
        "linkedin.com/in/ada",
        "30 days",
        "authorized",
    ):
        assert secret not in text
