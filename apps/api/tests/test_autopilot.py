"""Autopilot orchestration: recommendation -> save -> tailor -> auto-approve -> apply ->
tracker applied -> digest, on fixtures (fake agent, mock ATS on 127.0.0.1)."""

from datetime import UTC, datetime

import pytest
from sqlalchemy import select

from app.agent.tailor import AgentResult, DraftResult
from app.core.clock import local_day
from app.models.application import Application
from app.models.discovery import Recommendation
from app.models.job import AgentRun, UserAnswer
from app.models.run import Approval
from app.models.tracker import TrackerCard
from app.repositories.manager import RepositoryManager
from app.schemas.job import JobDescription
from app.schemas.run import Coverage, Pages, Violation
from app.services import autopilot as ap
from app.tasks import runs as run_tasks
from app.tasks.queue import RecordingQueue
from tests.apply_helpers import (
    PROFILE,
    api_as,
    enable_apply,
    make_apply_ctx,
    needs_chrome,
)
from tests.discovery_helpers import jd_for, make_catalog
from tests.jobs_helpers import approve_profile, make_ctx, make_user
from tests.runs_helpers import FakeAgent, ask, tailored

V = "2026-11"


@pytest.fixture(autouse=True)
def _apply(monkeypatch):
    enable_apply(monkeypatch)


def autopilot_user(db, **over):
    user = make_user(db)
    approve_profile(db, user, PROFILE)
    user.autopilot = {"enabled": True, "ack_version": V, "min_score": 70} | over
    db.commit()
    return user


def recommend(db, user, url, *, score=88, title="Backend Engineer", jd=None, ext="x1"):
    cat = make_catalog(
        db, title=title, external_id=ext, jd=jd or jd_for(title, must=("Python",))
    )
    cat.apply_url = url
    rec = Recommendation(
        user_id=user.id, catalog_job_id=cat.id, score=score, digest_date=local_day()
    )
    db.add(rec)
    db.commit()
    return rec, cat


def tctx(db, tmp_path, agent=None):
    return make_ctx(db, tmp_path, agent=agent or FakeAgent(), queue=RecordingQueue())


def tick_and_tailor(db, tmp_path, user, agent=None):
    ctx = tctx(db, tmp_path, agent)
    stats = ap.autopilot_tick(ctx, user.id)
    runs = db.scalars(select(AgentRun).where(AgentRun.user_id == user.id)).all()
    for r in runs:
        run_tasks.tailor(ctx, user.id, r.id)
    return ctx, stats, runs


def flagged_agent():
    return FakeAgent(
        AgentResult(
            drafts=[
                DraftResult(
                    tailored=tailored(),
                    violations=[
                        Violation(code="invented_number", field="bullet", message="x")
                    ],
                    coverage=Coverage(covered=["Python"], missing=[], pct=1.0),
                    pages=Pages(count=1, last_page_fill=0.5),
                )
            ]
        )
    )


@needs_chrome
def test_end_to_end_recommendation_to_applied_and_digest(db_session, tmp_path, ats):
    user = autopilot_user(db_session)
    rec, _cat = recommend(db_session, user, ats.base + "/greenhouse/jobs/1")
    user.preferences = {"notice_days": 30}
    db_session.commit()
    ctx, stats, runs = tick_and_tailor(db_session, tmp_path, user)
    assert stats["saved"] == 1 and stats["tailored"] == 1
    db_session.refresh(rec)
    assert rec.action == "saved"
    run = runs[0]
    assert run.autopilot is True
    db_session.refresh(run)
    assert run.status == "in_review" and not run.flagged
    assert (
        "autopilot_advance",
        {"user_id": str(user.id), "run_id": run.id},
    ) in ctx.queue.calls

    assert (
        ap.autopilot_advance(ctx, user.id, run.id) is True
    )  # renders, approves, creates
    db_session.refresh(run)
    assert run.status == "approved"
    app = db_session.scalar(select(Application))
    assert (
        app.status == "queued"
        and app.mode == "autopilot"
        and app.apply_url == ats.base + "/greenhouse/jobs/1"
    )

    from app.apply.runner import run_application

    run_application(make_apply_ctx(db_session, tmp_path), user.id, app.id)
    db_session.refresh(app)
    assert app.status == "submitted", app.skip_reason
    assert len(ats.submissions) == 1
    card = db_session.scalar(
        select(TrackerCard).where(TrackerCard.job_id == app.job_id)
    )
    assert card.column == "applied" and card.applied_at

    d = api_as(user.auth0_sub).get(f"/autopilot/digest?date={local_day()}").json()
    assert [i["application_id"] for i in d["submitted"]] == [app.id]
    assert d["skipped"] == [] and d["needs_a_person"] == []


def test_flagged_draft_is_never_approved_or_applied(db_session, tmp_path):
    user = autopilot_user(db_session)
    recommend(db_session, user, "https://boards.greenhouse.io/acme/jobs/1")
    ctx, _stats, runs = tick_and_tailor(db_session, tmp_path, user, flagged_agent())
    run = runs[0]
    db_session.refresh(run)
    assert run.status == "in_review"
    assert ap.autopilot_advance(ctx, user.id, run.id) is True
    db_session.refresh(run)
    assert run.status == "in_review"  # left for a person
    assert db_session.query(Approval).count() == 0
    app = db_session.scalar(select(Application))
    assert app.status == "skipped" and app.skip_reason == "draft_flagged"
    assert app.apply_url == "https://boards.greenhouse.io/acme/jobs/1"
    d = api_as(user.auth0_sub).get("/autopilot/digest").json()
    assert (
        d["skipped"][0]["reason"] == "draft_flagged" and d["skipped"][0]["direct_link"]
    )


def test_low_coverage_draft_is_skipped_too(db_session, tmp_path):
    user = autopilot_user(db_session)
    recommend(db_session, user, "https://boards.greenhouse.io/acme/jobs/1")
    low = FakeAgent(
        AgentResult(
            drafts=[
                DraftResult(
                    tailored=tailored(),
                    coverage=Coverage(covered=[], missing=["Go"], pct=0.1),
                    pages=Pages(),
                )
            ]
        )
    )
    ctx, _, runs = tick_and_tailor(db_session, tmp_path, user, low)
    ap.autopilot_advance(ctx, user.id, runs[0].id)
    assert db_session.scalar(select(Application)).skip_reason == "draft_flagged"
    assert db_session.query(Approval).count() == 0


def test_ask_user_is_answered_not_in_profile_without_interrupting(db_session, tmp_path):
    user = autopilot_user(db_session)
    recommend(db_session, user, "https://boards.greenhouse.io/acme/jobs/1")
    agent = FakeAgent(ask("Kubernetes"))
    ctx, _, runs = tick_and_tailor(db_session, tmp_path, user, agent)
    run = runs[0]
    db_session.refresh(run)
    assert run.status == "waiting_for_user"
    assert ap.autopilot_advance(ctx, user.id, run.id) is True
    db_session.refresh(run)
    assert run.status == "queued" and run.pending_questions == []
    row = db_session.scalar(select(UserAnswer))
    assert (row.skill, row.answer, row.detail) == ("kubernetes", "no", None)
    assert (
        "tailor",
        {"user_id": str(user.id), "run_id": run.id, "resume": True},
    ) in ctx.queue.calls


def test_manual_runs_are_never_auto_approved(db_session, tmp_path):
    from tests.runs_helpers import run_ready

    user = autopilot_user(db_session)
    run = run_ready(db_session, tmp_path, user)  # a person's own run
    assert run.autopilot is False
    assert ap.autopilot_advance(tctx(db_session, tmp_path), user.id, run.id) is False
    assert db_session.query(Approval).count() == 0


def test_gates_min_score_red_flags_and_off_switch(db_session, tmp_path):
    user = autopilot_user(db_session)
    recommend(db_session, user, "https://x.test/a", score=60, ext="low")
    recommend(db_session, user, "https://x.test/b", ext="flag", title="Flagged",
              jd=JobDescription(title="Flagged", company="Acme", must_have=["Python"], red_flags=["unpaid trial"]))  # fmt: skip
    ctx = tctx(db_session, tmp_path)
    assert ap.autopilot_tick(ctx, user.id) == {"saved": 0, "tailored": 0, "advanced": 0}
    assert db_session.query(AgentRun).count() == 0
    user.autopilot = {**user.autopilot, "enabled": False}
    db_session.commit()
    recommend(db_session, user, "https://x.test/c", ext="ok", title="Fine")
    assert ap.autopilot_tick(ctx, user.id)["saved"] == 0  # autopilot is off
    # an acknowledgement of an older policy text does not count
    user.autopilot = {**user.autopilot, "enabled": True, "ack_version": "2020-01"}
    db_session.commit()
    assert ap.autopilot_tick(ctx, user.id)["saved"] == 0


def test_tailoring_respects_the_daily_run_cap(db_session, tmp_path):
    user = autopilot_user(db_session)
    user.preferences = {"daily_cap": 1}
    db_session.commit()
    for i in range(3):
        recommend(
            db_session, user, f"https://x.test/{i}", ext=f"e{i}", title=f"Role {i}"
        )
    stats = ap.autopilot_tick(tctx(db_session, tmp_path), user.id)
    assert stats["saved"] == 3 and stats["tailored"] == 1
    assert db_session.query(AgentRun).count() == 1
    assert (
        ap.autopilot_tick(tctx(db_session, tmp_path), user.id)["tailored"] == 0
    )  # idempotent


def test_tick_is_idempotent_and_never_creates_a_second_application(
    db_session, tmp_path
):
    user = autopilot_user(db_session)
    recommend(db_session, user, "https://boards.greenhouse.io/acme/jobs/1")
    ctx, _, runs = tick_and_tailor(db_session, tmp_path, user)
    ap.autopilot_advance(ctx, user.id, runs[0].id)
    ap.autopilot_tick(ctx, user.id)
    ap.autopilot_advance(ctx, user.id, runs[0].id)
    assert (
        db_session.query(Application).count() == 1
        and db_session.query(Approval).count() == 1
    )


def test_extension_site_without_opt_in_is_skipped_with_a_link(db_session, tmp_path):
    user = autopilot_user(db_session)
    recommend(db_session, user, "https://wellfound.com/jobs/5-x")
    ctx, _, runs = tick_and_tailor(db_session, tmp_path, user)
    ap.autopilot_advance(ctx, user.id, runs[0].id)
    app = db_session.scalar(select(Application))
    assert app.status == "skipped" and app.skip_reason == "site_not_opted_in"
    assert app.apply_url == "https://wellfound.com/jobs/5-x"


def test_daily_digest_is_sent_once_after_digest_time(db_session, tmp_path):
    user = autopilot_user(db_session, digest_time="00:00")
    sent = []

    class Mail:
        def send(self, user_id, template, **params):
            sent.append((user_id, template, params))

    ctx = make_ctx(db_session, tmp_path, mailer=Mail())
    now = datetime.now(UTC)
    assert ap.send_digests(ctx, now) == 1
    assert ap.send_digests(ctx, now) == 0  # once per day
    assert sent[0][1] == "autopilot_digest" and sent[0][0] == str(user.id)
    db_session.refresh(user)
    assert user.autopilot["last_digest_date"] == local_day(now)
    # before the configured time nothing goes out
    user.autopilot = {
        **user.autopilot,
        "last_digest_date": None,
        "digest_time": "23:59",
    }
    db_session.commit()
    early = datetime(2026, 11, 19, 3, 0, tzinfo=UTC)  # 08:30 IST
    assert ap.send_digests(ctx, early) == 0


def test_digest_date_validation(db_session):
    make_user(db_session)
    assert api_as("auth0|A").get("/autopilot/digest?date=nope").status_code == 422


def test_cli_schedule_prints_cron(capsys):
    from app.apply import cli

    assert cli.main(["schedule"]) == 0
    out = capsys.readouterr().out
    assert "app.apply.cli tick" in out and "CRON_TZ=Asia/Kolkata" in out


def test_repository_manager_user_filter(db_session):
    make_user(db_session)
    assert RepositoryManager(db_session).applications.autopilot_user_ids() == []
