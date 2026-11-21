from datetime import timedelta

import httpx
from sqlalchemy import func, select

from app.discovery import pipeline, tasks
from app.discovery.lists_loader import sync_lists
from app.models.discovery import CatalogJob, Company
from app.tasks.queue import RecordingQueue
from tests.discovery_helpers import (
    NOW,
    Router,
    fixture,
    jd_for,
    jr,
    make_catalog,
    make_dctx,
)
from tests.jobs_helpers import FakeExtractor, approve_profile, make_user

GH = "https://boards-api.greenhouse.io/v1/boards/acme/jobs"


def add_company(
    db, name="Acme", ats="greenhouse", token="acme", careers="https://acme.test/careers"
):
    c = Company(
        name=name,
        name_key=name.lower(),
        ats=ats,
        board_token=token,
        careers_url=careers,
        lists=["yc"],
    )
    db.add(c)
    db.commit()
    return c


def count(db, model=CatalogJob):
    return db.scalar(select(func.count()).select_from(model))


def gh_router():
    return Router().add(f"{GH}/", jr({}))  # is_open default; list route below


def board_router():
    r = Router()
    r.add(GH, lambda req: jr(fixture("greenhouse_board.json")))
    return r


# --- lists -----------------------------------------------------------------------
def test_sync_lists_is_idempotent_and_tags_companies(db_session):
    n = sync_lists(db_session)
    rows = count(db_session, Company)
    assert n >= 9 and rows == n
    assert sync_lists(db_session) == n and count(db_session, Company) == rows
    razor = db_session.scalar(select(Company).where(Company.name == "Razorpay"))
    assert razor.lists == ["yc"] and razor.ats == "unknown"
    sarvam = db_session.scalar(select(Company).where(Company.name == "Sarvam AI"))
    assert sarvam.lists == ["india_ai"]


# --- upsert / extract once ----------------------------------------------------------
def test_sync_upserts_idempotently_and_extracts_once(db_session, tmp_path):
    co = add_company(db_session)
    ex = FakeExtractor(jd_for())
    d = make_dctx(db_session, tmp_path, board_router(), extractor=ex)
    tasks.sync_source(d, company_id=co.id)
    assert count(db_session) == 2 and len(ex.calls) == 2
    rows = list(db_session.scalars(select(CatalogJob)))
    assert all(r.jd and r.embedding and r.embedding_model for r in rows)
    first_seen = {r.id: r.first_seen for r in rows}

    d.now = lambda: NOW + timedelta(days=1)
    tasks.sync_source(d, company_id=co.id)
    db_session.expire_all()
    assert count(db_session) == 2
    assert len(ex.calls) == 2  # unchanged content: no second extraction
    for r in db_session.scalars(select(CatalogJob)):
        assert r.first_seen == first_seen[r.id]
        assert r.last_seen.replace(tzinfo=None) == (NOW + timedelta(days=1)).replace(
            tzinfo=None
        )


def test_changed_content_reextracts_only_that_posting(db_session, tmp_path):
    co = add_company(db_session)
    board = fixture("greenhouse_board.json")
    r = Router().add(GH, lambda req: jr(board))
    ex = FakeExtractor(jd_for())
    d = make_dctx(db_session, tmp_path, r, extractor=ex)
    tasks.sync_source(d, company_id=co.id)
    board["jobs"][0]["content"] = (
        "&lt;p&gt;Python and Postgres, now with Rust.&lt;/p&gt;"
    )
    tasks.sync_source(d, company_id=co.id)
    assert len(ex.calls) == 3
    assert count(db_session) == 2


def test_identical_text_across_sources_is_extracted_once(db_session, tmp_path):
    a = make_catalog(db_session, title="Dev", external_id="1", embed=False)
    b = make_catalog(db_session, title="Dev", external_id="2", embed=False)
    for r in (a, b):
        r.jd, r.content_hash = None, "same"
    db_session.commit()
    ex = FakeExtractor(jd_for("Dev"))
    d = make_dctx(db_session, tmp_path, extractor=ex)
    assert pipeline.enrich(d) == 2
    assert len(ex.calls) == 1


def test_failed_extraction_is_retried_next_run(db_session, tmp_path):
    co = add_company(db_session)
    ex = FakeExtractor(jd_for(), errors=[RuntimeError("x")])
    d = make_dctx(db_session, tmp_path, board_router(), extractor=ex)
    tasks.sync_source(d, company_id=co.id)
    assert sum(1 for r in db_session.scalars(select(CatalogJob)) if r.jd) == 1
    tasks.sync_source(d, company_id=co.id)
    assert all(r.jd for r in db_session.scalars(select(CatalogJob)))
    assert len(ex.calls) == 3


def test_board_404_marks_company_for_redetection(db_session, tmp_path):
    co = add_company(db_session)
    d = make_dctx(db_session, tmp_path, Router())  # everything 404s
    assert tasks.sync_source(d, company_id=co.id) == 0
    db_session.expire_all()
    assert db_session.get(Company, co.id).redetect is True


def test_himalayas_sync_creates_company_and_keeps_attribution(db_session, tmp_path):
    r = Router().add(
        "https://himalayas.app/jobs/api/search", jr(fixture("himalayas_search_p2.json"))
    )
    d = make_dctx(db_session, tmp_path, r)
    tasks.sync_source(d, source="himalayas")
    tasks.sync_source(d, source="himalayas")
    rows = list(db_session.scalars(select(CatalogJob)))
    assert len(rows) == 3 and count(db_session, Company) == 1
    assert all(
        x.source == "himalayas" and x.source_attribution["provider"] == "Himalayas"
        for x in rows
    )
    assert all(x.apply_url.endswith("/apply") and x.remote for x in rows)
    assert r.calls[0].url.params["country"] == "India"


# --- dedupe ------------------------------------------------------------------------------
def test_dedupe_keeps_the_employer_ats_record(db_session, tmp_path):
    ats = make_catalog(
        db_session,
        title="Senior Python Engineer",
        external_id="a",
        remote=True,
        city=None,
    )
    him = make_catalog(
        db_session,
        title="Senior  Python engineer!",
        external_id="b",
        source="himalayas",
        remote=True,
        city=None,
        first_seen=NOW + timedelta(days=5),
    )
    other = make_catalog(db_session, title="Designer", external_id="c")
    d = make_dctx(db_session, tmp_path)
    assert pipeline.dedupe(d) == 1
    db_session.expire_all()
    assert (
        him.duplicate_of == ats.id
        and ats.duplicate_of is None
        and other.duplicate_of is None
    )
    assert pipeline.dedupe(d) == 0  # idempotent


def test_dedupe_ignores_postings_more_than_30_days_apart(db_session, tmp_path):
    a = make_catalog(db_session, title="Eng", external_id="a")
    b = make_catalog(
        db_session, title="Eng", external_id="b", first_seen=NOW + timedelta(days=45)
    )
    pipeline.dedupe(make_dctx(db_session, tmp_path))
    db_session.expire_all()
    assert a.duplicate_of is None and b.duplicate_of is None


# --- sweep ----------------------------------------------------------------------------------
def test_sweep_closes_postings_that_are_gone_and_keeps_live_ones(db_session, tmp_path):
    co = add_company(db_session)
    old = NOW - timedelta(days=5)
    gone = make_catalog(db_session, title="Gone", external_id="1", first_seen=old)
    live = make_catalog(db_session, title="Live", external_id="2", first_seen=old)
    fresh = make_catalog(db_session, title="Fresh", external_id="3", first_seen=NOW)
    for r in (gone, live, fresh):
        r.company_id = co.id
    db_session.commit()
    r = Router().add(f"{GH}/1", httpx.Response(404)).add(f"{GH}/2", jr({}))
    d = make_dctx(db_session, tmp_path, r)
    assert pipeline.sweep_closed(d) == 1
    db_session.expire_all()
    assert gone.closed_at is not None
    assert live.closed_at is None and live.last_seen.replace(
        tzinfo=None
    ) == NOW.replace(tzinfo=None)
    assert fresh.closed_at is None
    assert not any(u.endswith("/3") for u in r.urls())  # recently seen: not checked


def test_sweep_leaves_posting_open_when_the_check_errors(db_session, tmp_path):
    co = add_company(db_session)
    row = make_catalog(
        db_session, title="X", external_id="9", first_seen=NOW - timedelta(days=9)
    )
    row.company_id = co.id
    db_session.commit()
    d = make_dctx(db_session, tmp_path, Router().add(GH, httpx.Response(500)))
    assert pipeline.sweep_closed(d) == 0
    db_session.expire_all()
    assert row.closed_at is None


def test_himalayas_410_closes(db_session, tmp_path):
    row = make_catalog(
        db_session,
        title="H",
        source="himalayas",
        external_id="acme-labs/old",
        first_seen=NOW - timedelta(days=9),
        remote=True,
    )
    r = Router().add(
        "https://himalayas.app/jobs/api/companies/acme-labs/jobs/old",
        httpx.Response(410),
    )
    assert pipeline.sweep_closed(make_dctx(db_session, tmp_path, r)) == 1
    db_session.expire_all()
    assert row.closed_at is not None


# --- detection ---------------------------------------------------------------------------------
def test_detect_ats_saves_board_and_clears_redetect(db_session, tmp_path):
    co = Company(
        name="Beta",
        name_key="beta",
        careers_url="https://beta.test/careers",
        ats="unknown",
        redetect=True,
        lists=[],
    )
    db_session.add(co)
    db_session.commit()
    r = (
        Router()
        .add("https://beta.test/robots.txt", httpx.Response(404))
        .add(
            "https://beta.test/careers",
            httpx.Response(200, text=fixture("careers_lever.html")),
        )
    )
    assert tasks.detect_ats(make_dctx(db_session, tmp_path, r), company_id=co.id)
    db_session.expire_all()
    assert (co.ats, co.board_token, co.redetect) == ("lever", "beta", False)
    assert co.last_detected_at is not None


def test_detect_stale_runs_monthly(db_session, tmp_path):
    co = Company(
        name="Beta",
        name_key="beta",
        careers_url="https://beta.test/careers",
        ats="lever",
        board_token="beta",
        lists=[],
        last_detected_at=NOW - timedelta(days=5),
    )
    db_session.add(co)
    db_session.commit()
    r = Router()
    assert pipeline.detect_stale(make_dctx(db_session, tmp_path, r)) == 0
    assert r.calls == []  # detected 5 days ago: not due
    co.last_detected_at = NOW - timedelta(days=40)
    db_session.commit()
    pipeline.detect_stale(make_dctx(db_session, tmp_path, r))
    assert r.calls  # due again


# --- daily pipeline -------------------------------------------------------------------------------
def test_run_daily_runs_every_step_and_queues_users(db_session, tmp_path):
    co = add_company(db_session)
    a = make_user(db_session, "auth0|A")
    make_user(db_session, "auth0|B")  # no approved profile: not queued
    approve_profile(db_session, a)
    r = (
        Router()
        .add(GH, lambda req: jr(fixture("greenhouse_board.json")))
        .add(
            "https://himalayas.app/jobs/api/search",
            jr(fixture("himalayas_search_p2.json")),
        )
    )
    q = RecordingQueue()
    d = make_dctx(db_session, tmp_path, r, queue=q)
    stats = tasks.sync_catalog(d)
    assert stats["seen"] == 5 and stats["enriched"] == 5
    assert q.calls == [("build_recommendations", {"user_id": str(a.id)})]
    assert (
        db_session.get(Company, co.id).ats == "greenhouse"
    )  # a failed detection keeps the board


def test_pipeline_tasks_are_registered():
    from app.tasks.runtime import registry

    names = set(registry())
    assert {
        "sync_source",
        "detect_ats",
        "sweep_closed",
        "build_recommendations",
        "sync_catalog",
        "sync_lists",
    } <= names


def test_cli_prints_schedule(capsys):
    from app.discovery.cli import main

    assert main(["schedule"]) == 0
    out = capsys.readouterr().out
    assert "Asia/Kolkata" in out and "run-daily" in out
