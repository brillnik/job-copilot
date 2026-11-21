"""Applications, Autopilot settings, manual apply and the extension channel (API level;
no browser)."""

import pytest
from sqlalchemy import select

from app.core.config import settings
from app.models.application import Application, SiteState
from app.models.job import Event
from app.models.tracker import TrackerCard
from app.repositories.manager import RepositoryManager
from tests.apply_helpers import PROFILE, api_as, approved_run
from tests.jobs_helpers import make_user
from tests.test_extension import bearer, paired

GH = "https://boards.greenhouse.io/acme/jobs/1"
V = settings.autopilot_policy_version


@pytest.fixture(autouse=True)
def _reset():
    from tests.test_extension import ext

    ext.throttle._hits.clear()


def opt_in(client, *sites):
    body = {"sites": {s: {"opt_in": True, "acknowledgement_version": V} for s in sites}}
    r = client.put("/autopilot", json=body)
    assert r.status_code == 200, r.text
    return r


# --- Autopilot settings ---------------------------------------------------------------
def test_autopilot_is_off_by_default(db_session):
    make_user(db_session)
    r = api_as("auth0|A").get("/autopilot").json()
    assert r["enabled"] is False and r["min_score"] == 75 and r["daily_apply_cap"] == 15
    assert all(not s["acknowledged"] for s in r["sites_opt_in"].values())


def test_enabling_needs_the_current_policy_version(db_session):
    make_user(db_session)
    c = api_as("auth0|A")
    for body in (
        {"enabled": True},
        {"enabled": True, "acknowledgement_version": "old"},
    ):
        r = c.put("/autopilot", json=body)
        assert r.status_code == 422 and r.json()["code"] == "acknowledgement_required"
    assert c.get("/autopilot").json()["enabled"] is False
    r = c.put(
        "/autopilot",
        json={"enabled": True, "acknowledgement_version": V, "min_score": 80},
    )
    assert r.json()["enabled"] is True and r.json()["min_score"] == 80
    assert c.put("/autopilot", json={"enabled": False}).json()["enabled"] is False


def test_each_site_needs_its_own_acknowledgement(db_session):
    make_user(db_session)
    c = api_as("auth0|A")
    r = c.put("/autopilot", json={"sites": {"wellfound": {"opt_in": True}}})
    assert r.status_code == 422 and r.json()["code"] == "acknowledgement_required"
    # the autopilot acknowledgement does not cover a site
    r = c.put("/autopilot", json={"enabled": True, "acknowledgement_version": V,
                                  "sites": {"naukri": {"opt_in": True}}})  # fmt: skip
    assert r.status_code == 422
    r = opt_in(c, "wellfound").json()
    w = r["sites_opt_in"]["wellfound"]
    assert w["acknowledged"] and w["acknowledged_at"] and w["policy_version"] == V
    assert not r["sites_opt_in"]["naukri"]["acknowledged"]
    r = c.put("/autopilot", json={"sites": {"wellfound": {"opt_in": False}}}).json()
    assert not r["sites_opt_in"]["wellfound"]["acknowledged"]


def test_daily_cap_is_clamped_and_unknown_sites_rejected(db_session):
    make_user(db_session)
    c = api_as("auth0|A")
    assert (
        c.put("/autopilot", json={"daily_apply_cap": 999}).json()["daily_apply_cap"]
        == settings.autopilot_daily_cap_max
    )
    assert (
        c.put("/autopilot", json={"sites": {"linkedin": {"opt_in": True}}}).status_code
        == 422
    )
    assert c.put("/autopilot", json={"digest_time": "25:00"}).status_code == 422


# --- manual apply -----------------------------------------------------------------------
def test_apply_requires_an_approved_run(db_session, tmp_path):
    from tests.runs_helpers import run_ready

    user = make_user(db_session)
    run = run_ready(db_session, tmp_path, user)  # in_review, not approved
    r = api_as("auth0|A").post(f"/runs/{run.id}/apply")
    assert r.status_code == 409 and r.json()["code"] == "run_not_approved"


def test_apply_creates_one_queued_application_per_job(db_session, tmp_path, queue):
    user = make_user(db_session)
    _job, run = approved_run(db_session, tmp_path, user, GH)
    c = api_as("auth0|A")
    r = c.post(f"/runs/{run.id}/apply")
    assert r.status_code == 202, r.text
    a = r.json()
    assert (
        a["status"] == "queued"
        and a["channel"] == "playwright"
        and a["ats"] == "greenhouse"
    )
    assert a["mode"] == "manual" and a["direct_link"] == GH
    assert c.post(f"/runs/{run.id}/apply").json()["id"] == a["id"]
    assert db_session.query(Application).count() == 1
    assert queue.calls == []  # external worker mode: the API only queues the row


def test_inprocess_mode_enqueues_the_apply_task(
    db_session, tmp_path, queue, monkeypatch
):
    monkeypatch.setattr(settings, "apply_worker_mode", "inprocess")
    user = make_user(db_session)
    _job, run = approved_run(db_session, tmp_path, user, GH)
    a = api_as("auth0|A").post(f"/runs/{run.id}/apply").json()
    assert queue.calls[-1] == (
        "apply_application",
        {"user_id": str(user.id), "application_id": a["id"]},
    )


def test_linkedin_and_missing_links_are_refused(db_session, tmp_path):
    user = make_user(db_session)
    _job, run = approved_run(
        db_session, tmp_path, user, "https://www.linkedin.com/jobs/view/1"
    )
    r = api_as("auth0|A").post(f"/runs/{run.id}/apply")
    assert r.status_code == 422
    assert db_session.query(Application).count() == 0


def test_kill_switches_refuse_manual_apply(db_session, tmp_path, monkeypatch):
    user = make_user(db_session)
    _job, run = approved_run(db_session, tmp_path, user, GH)
    c = api_as("auth0|A")
    monkeypatch.setattr(settings, "apply_enabled", False)
    assert c.post(f"/runs/{run.id}/apply").json()["code"] == "kill_switch"
    monkeypatch.setattr(settings, "apply_enabled", True)
    monkeypatch.setattr(settings, "apply_enabled_ats", ["lever"])
    assert c.post(f"/runs/{run.id}/apply").json()["code"] == "ats_disabled"
    assert db_session.query(Application).count() == 0


def test_extension_sites_need_an_acknowledged_opt_in(db_session, tmp_path):
    user = make_user(db_session)
    _job, run = approved_run(
        db_session, tmp_path, user, "https://wellfound.com/jobs/77-x"
    )
    c = api_as("auth0|A")
    r = c.post(f"/runs/{run.id}/apply")
    assert r.status_code == 409 and r.json()["code"] == "site_not_opted_in"
    opt_in(c, "wellfound")
    a = c.post(f"/runs/{run.id}/apply").json()
    assert (
        a["channel"] == "extension"
        and a["site"] == "wellfound"
        and a["status"] == "queued"
    )


def test_stale_policy_version_cancels_the_opt_in(db_session, tmp_path, monkeypatch):
    user = make_user(db_session)
    _job, run = approved_run(
        db_session, tmp_path, user, "https://wellfound.com/jobs/77-x"
    )
    c = api_as("auth0|A")
    opt_in(c, "wellfound")
    monkeypatch.setattr(settings, "autopilot_policy_version", "2027-01")
    assert c.post(f"/runs/{run.id}/apply").json()["code"] == "site_not_opted_in"


# --- /applications ------------------------------------------------------------------------
def test_list_detail_cancel_and_answer_state_rules(db_session, tmp_path):
    user = make_user(db_session)
    _job, run = approved_run(db_session, tmp_path, user, GH)
    c = api_as("auth0|A")
    a = c.post(f"/runs/{run.id}/apply").json()
    assert [x["id"] for x in c.get("/applications").json()["items"]] == [a["id"]]
    assert c.get("/applications?status=submitted").json()["items"] == []
    assert c.get(f"/applications/{a['id']}").json()["company"] == "Globex Corp"
    r = c.post(
        f"/applications/{a['id']}/answer",
        json={"answers": [{"key": "x", "value": "y"}]},
    )
    assert r.status_code == 409 and r.json()["code"] == "invalid_state"
    r = c.post(f"/applications/{a['id']}/cancel")
    assert r.status_code == 200 and r.json()["status"] == "cancelled"
    assert c.post(f"/applications/{a['id']}/cancel").status_code == 409
    # a cancelled one can be started again manually
    again = c.post(f"/runs/{run.id}/apply").json()
    assert again["id"] == a["id"] and again["status"] == "queued"


def test_answer_validates_keys_and_resumes(db_session, tmp_path):
    user = make_user(db_session)
    _job, run = approved_run(db_session, tmp_path, user, GH)
    c = api_as("auth0|A")
    a = c.post(f"/runs/{run.id}/apply").json()
    row = db_session.get(Application, a["id"])
    row.status = "waiting_for_user"
    row.pending_fields = [
        {
            "key": "wa",
            "label": "Authorized to work?",
            "kind": "text",
            "field_type": "work_authorization",
            "options": [],
        }
    ]
    db_session.commit()
    assert c.get(f"/applications/{a['id']}").json()["pending_fields"][0]["key"] == "wa"
    bad = c.post(
        f"/applications/{a['id']}/answer",
        json={"answers": [{"key": "nope", "value": "Yes"}]},
    )
    assert bad.status_code == 422
    ok = c.post(
        f"/applications/{a['id']}/answer",
        json={"answers": [{"key": "wa", "value": "Yes"}]},
    )
    assert ok.status_code == 202 and ok.json()["status"] == "queued"
    db_session.refresh(row)
    assert row.provided_answers and row.pending_fields == []
    # remembered in the screening-answer bank for next time
    from app.models.screening import ScreeningAnswer

    assert (
        db_session.query(ScreeningAnswer)
        .filter_by(user_id=user.id, source="user")
        .count()
        == 1
    )


def test_every_application_endpoint_is_isolated(db_session, tmp_path):
    a = make_user(db_session, "auth0|A")
    make_user(db_session, "auth0|B")
    _job, run = approved_run(db_session, tmp_path, a, GH)
    app_id = api_as("auth0|A").post(f"/runs/{run.id}/apply").json()["id"]
    b = api_as("auth0|B")
    assert b.get("/applications").json()["items"] == []
    assert b.get(f"/applications/{app_id}").status_code == 404
    assert b.post(f"/applications/{app_id}/cancel").status_code == 404
    assert (
        b.post(
            f"/applications/{app_id}/answer",
            json={"answers": [{"key": "k", "value": "v"}]},
        ).status_code
        == 404
    )
    assert b.post(f"/runs/{run.id}/apply").status_code == 404
    assert api_as("auth0|A").get(f"/applications/{app_id}").status_code == 200
    d = b.get("/autopilot/digest").json()
    assert d["submitted"] == d["skipped"] == d["needs_a_person"] == []


# --- extension channel -----------------------------------------------------------------------
def ext_setup(
    db_session,
    tmp_path,
    *,
    sub="auth0|A",
    url="https://www.naukri.com/job-listings-x-1",
    profile=PROFILE,
):
    user = make_user(db_session, sub)
    job, run = approved_run(
        db_session, tmp_path, user, url, profile=profile, prefs={"notice_days": 15}
    )
    c = api_as(sub)
    token = paired(db_session, sub)["token"]
    return user, job, run, c, token


def test_apply_queue_only_lists_opted_in_sites_within_caps(db_session, tmp_path):
    user, _job, run, c, token = ext_setup(db_session, tmp_path)
    app_id = None
    opt_in(c, "naukri")
    app_id = c.post(f"/runs/{run.id}/apply").json()["id"]
    from tests.test_extension import client as raw

    q = raw.get("/extension/apply-queue", headers=bearer(token))
    assert q.status_code == 200 and [x["id"] for x in q.json()] == [app_id]
    # opt-out: nothing is ever queued for the extension
    c.put("/autopilot", json={"sites": {"naukri": {"opt_in": False}}})
    assert raw.get("/extension/apply-queue", headers=bearer(token)).json() == []
    opt_in(c, "naukri")
    # site cap reached: not offered
    from app.core.clock import local_day
    from app.models.application import ApplyQuota

    db_session.add(
        ApplyQuota(
            user_id=user.id,
            day=local_day(),
            site="naukri",
            used=settings.autopilot_site_caps["naukri"],
        )
    )
    db_session.commit()
    assert raw.get("/extension/apply-queue", headers=bearer(token)).json() == []


def test_extension_auth_is_device_token_only(db_session, tmp_path):
    _user, _job, _run, _c, token = ext_setup(db_session, tmp_path)
    from tests.test_extension import client as raw

    assert raw.get("/extension/apply-queue").status_code == 401
    from app.core.security import token_claims
    from app.main import app as fastapi_app

    fastapi_app.dependency_overrides.pop(
        token_claims
    )  # real JWT check on normal routes
    assert (
        raw.get("/applications", headers=bearer(token)).status_code == 401
    )  # not valid elsewhere
    assert (
        raw.get("/extension/apply-plan/x", headers=bearer("jce_bogus")).status_code
        == 401
    )


def test_apply_plan_lists_unmapped_required_fields_and_reserves_a_slot(
    db_session, tmp_path
):
    no_phone = PROFILE.model_copy(
        update={"contact": PROFILE.contact.model_copy(update={"phone": None})}
    )
    _user, _job, run, c, token = ext_setup(db_session, tmp_path, profile=no_phone)
    opt_in(c, "naukri")
    app_id = c.post(f"/runs/{run.id}/apply").json()["id"]
    from tests.test_extension import client as raw

    r = raw.get(
        f"/extension/apply-plan/{app_id}?required=expected_ctc&required=notice_period",
        headers=bearer(token),
    )
    assert r.status_code == 200, r.text
    plan = r.json()
    assert (
        plan["contact"]["name"] == "Ada Lovelace"
        and plan["contact"]["email"] == "ada@example.com"
    )
    assert plan["answers"]["notice_period"] == {
        "value": "15 days",
        "source": "settings",
    }
    assert set(plan["required_without_value"]) == {
        "phone",
        "expected_ctc",
    }  # naukri needs a phone
    assert plan["skip_if_required_without_value"] is True
    assert (
        plan["pdf_url"].startswith(("http", "/files/")) or "/files/" in plan["pdf_url"]
    )
    pdf = raw.get(plan["pdf_url"].replace("http://testserver", ""))
    assert pdf.status_code == 200 and pdf.content.startswith(b"%PDF")
    row = db_session.get(Application, app_id)
    assert row.status == "running" and row.slot_held and row.attempts == 1
    again = raw.get(f"/extension/apply-plan/{app_id}", headers=bearer(token))
    assert again.status_code == 200
    db_session.refresh(row)
    assert row.attempts == 1  # idempotent


def test_apply_plan_enforces_the_caps_and_isolation(db_session, tmp_path):
    user, _job, run, c, token = ext_setup(db_session, tmp_path)
    opt_in(c, "naukri")
    app_id = c.post(f"/runs/{run.id}/apply").json()["id"]
    from app.core.clock import local_day
    from app.models.application import ApplyQuota

    db_session.add(ApplyQuota(user_id=user.id, day=local_day(), site="naukri", used=5))
    db_session.commit()
    from tests.test_extension import client as raw

    r = raw.get(f"/extension/apply-plan/{app_id}", headers=bearer(token))
    assert r.status_code == 429 and r.json()["code"] == "cap_reached"
    # another user's device cannot touch it
    make_user(db_session, "auth0|B")
    other = paired(db_session, "auth0|B")["token"]
    assert (
        raw.get(f"/extension/apply-plan/{app_id}", headers=bearer(other)).status_code
        == 404
    )
    assert (
        raw.post(
            f"/extension/apply-result/{app_id}",
            json={"status": "submitted"},
            headers=bearer(other),
        ).status_code
        == 404
    )


def test_apply_result_submitted_has_the_same_post_submit_handling(db_session, tmp_path):
    user, job, run, c, token = ext_setup(db_session, tmp_path)
    opt_in(c, "naukri")
    app_id = c.post(f"/runs/{run.id}/apply").json()["id"]
    from tests.test_extension import client as raw

    early = raw.post(
        f"/extension/apply-result/{app_id}",
        json={"status": "submitted"},
        headers=bearer(token),
    )
    assert early.status_code == 409  # plan first: the cap slot is taken there
    raw.get(f"/extension/apply-plan/{app_id}", headers=bearer(token))
    import base64

    png = base64.b64encode(b"\x89PNG\r\n\x1a\nfake").decode()
    r = raw.post(
        f"/extension/apply-result/{app_id}",
        json={"status": "submitted", "screenshot": png},
        headers=bearer(token),
    )
    assert r.status_code == 200 and r.json()["status"] == "submitted"
    row = db_session.get(Application, app_id)
    assert row.slot_held and row.screenshot_keys[0].startswith(
        f"users/{user.id.hex}/applications/{app_id}/"
    )
    card = db_session.scalar(select(TrackerCard).where(TrackerCard.job_id == job.id))
    assert card.column == "applied" and card.applied_at
    assert db_session.scalars(select(Event).where(Event.type == "job_applied")).all()
    assert (
        raw.post(
            f"/extension/apply-result/{app_id}",
            json={"status": "submitted"},
            headers=bearer(token),
        ).status_code
        == 200
    )  # retried report


def test_apply_result_validates_the_screenshot(db_session, tmp_path):
    _user, _job, run, c, token = ext_setup(db_session, tmp_path)
    opt_in(c, "naukri")
    app_id = c.post(f"/runs/{run.id}/apply").json()["id"]
    from tests.test_extension import client as raw

    raw.get(f"/extension/apply-plan/{app_id}", headers=bearer(token))
    for bad in ("not base64!!", "aGVsbG8="):  # not base64 / not an image
        r = raw.post(
            f"/extension/apply-result/{app_id}",
            json={"status": "submitted", "screenshot": bad},
            headers=bearer(token),
        )
        assert r.status_code == 422
    assert db_session.get(Application, app_id).status == "running"


def test_error_and_skip_results_release_the_slot_and_repeated_blocks_pause_the_site(
    db_session, tmp_path
):
    user = make_user(db_session)
    c = api_as("auth0|A")
    opt_in(c, "naukri")
    token = paired(db_session, "auth0|A")["token"]
    from tests.test_extension import client as raw

    ids = []
    for i in range(3):
        _, run = approved_run(
            db_session, tmp_path, user, f"https://www.naukri.com/job-{i}"
        )
        ids.append(c.post(f"/runs/{run.id}/apply").json()["id"])
    repos = RepositoryManager(db_session)

    def report(app_id, body):
        raw.get(f"/extension/apply-plan/{app_id}", headers=bearer(token))
        return raw.post(
            f"/extension/apply-result/{app_id}", json=body, headers=bearer(token)
        )

    r = report(ids[0], {"status": "error", "reason": "timeout"})
    assert (
        r.json()["status"] == "failed"
        and not db_session.get(Application, ids[0]).slot_held
    )
    from app.core.clock import local_day

    assert repos.applications.used(user.id, local_day(), "naukri") == 0  # not counted
    report(ids[1], {"status": "skipped", "reason": "captcha"})
    assert repos.applications.paused_sites(user.id) == []
    report(ids[2], {"status": "skipped", "reason": "login"})
    assert repos.applications.paused_sites(user.id) == ["naukri"]
    assert c.get("/autopilot").json()["sites_opt_in"]["naukri"]["paused"] is True
    # paused: no queue, no plan, no manual apply
    _job, run = approved_run(db_session, tmp_path, user, "https://www.naukri.com/job-9")
    assert c.post(f"/runs/{run.id}/apply").json()["code"] == "site_paused"
    assert db_session.query(Application).filter_by(status="queued").count() == 0
    # the person can resume the site
    c.put("/autopilot", json={"resume_sites": ["naukri"]})
    assert repos.applications.paused_sites(user.id) == []
    assert c.post(f"/runs/{run.id}/apply").status_code == 202


def test_a_successful_submit_resets_the_block_streak(db_session, tmp_path):
    user = make_user(db_session)
    c = api_as("auth0|A")
    opt_in(c, "naukri")
    token = paired(db_session, "auth0|A")["token"]
    from tests.test_extension import client as raw

    ids = []
    for i in range(3):
        _job, run = approved_run(
            db_session, tmp_path, user, f"https://www.naukri.com/job-{i}"
        )
        ids.append(c.post(f"/runs/{run.id}/apply").json()["id"])
    for app_id, body in zip(
        ids,
        (
            {"status": "skipped", "reason": "captcha"},
            {"status": "submitted"},
            {"status": "skipped", "reason": "captcha"},
        ),
        strict=True,
    ):
        raw.get(f"/extension/apply-plan/{app_id}", headers=bearer(token))
        raw.post(f"/extension/apply-result/{app_id}", json=body, headers=bearer(token))
    assert RepositoryManager(db_session).applications.paused_sites(user.id) == []
    assert db_session.get(SiteState, (user.id, "naukri")).consecutive_blocks == 1


def test_the_server_never_fetches_denied_sites():
    import httpx

    from app.core.netguard import DeniedHost, guarded_client

    for url in (
        "https://wellfound.com/x",
        "https://www.naukri.com/x",
        "https://hiring.cafe/x",
        "https://linkedin.com/x",
    ):
        with pytest.raises(DeniedHost):
            guarded_client(
                transport=httpx.MockTransport(lambda r: httpx.Response(200))
            ).get(url)
