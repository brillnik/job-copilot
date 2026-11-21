import httpx
import pytest

from app.core.config import settings
from app.discovery.sources.ashby import AshbySource
from app.discovery.sources.base import BoardGone, SourceTarget
from app.discovery.sources.greenhouse import GreenhouseSource
from app.discovery.sources.himalayas import HimalayasSource
from app.discovery.sources.lever import LeverSource
from tests.discovery_helpers import Router, fixture, jr, make_fetcher

H = "https://himalayas.app/jobs/api"


def himalayas(router, **kw):
    return HimalayasSource(make_fetcher(router, **kw), "https://himalayas.app")


def test_himalayas_search_paginates_until_a_short_page():
    router = Router().add(
        f"{H}/search",
        lambda req: jr(
            fixture("himalayas_search_p1.json")
            if req.url.params["page"] == "1"
            else fixture("himalayas_search_p2.json")
        ),
    )
    jobs = list(
        himalayas(router).list_jobs(SourceTarget(country="India", query="python"))
    )
    assert len(jobs) == 23
    assert [c.url.params["page"] for c in router.calls] == ["1", "2"]
    assert router.calls[0].url.params["country"] == "India"
    assert router.calls[0].url.params["q"] == "python"


def test_himalayas_keeps_attribution_and_apply_link():
    router = Router().add(f"{H}/search", jr(fixture("himalayas_search_p2.json")))
    first = next(iter(himalayas(router).list_jobs(SourceTarget())))
    assert first.apply_url.endswith("/apply")  # applicationLink, never the listing URL
    assert first.source_attribution["provider"] == "Himalayas"
    assert first.source_attribution["url"].startswith(
        "https://himalayas.app/companies/"
    )
    assert first.external_id == "acme-labs/senior-python-engineer-20"
    assert first.country_restrictions == ["India", "Singapore"] and first.remote
    assert "Postgres" in first.raw_text and "<p>" not in first.raw_text


def test_himalayas_sends_bearer_when_configured(monkeypatch):
    monkeypatch.setattr(settings, "himalayas_api_key", "sekret")
    router = Router().add(f"{H}/search", jr({"jobs": []}))
    list(himalayas(router).list_jobs(SourceTarget()))
    assert router.calls[0].headers["authorization"] == "Bearer sekret"
    monkeypatch.setattr(settings, "himalayas_api_key", "")
    router.calls.clear()
    list(himalayas(router).list_jobs(SourceTarget()))
    assert "authorization" not in router.calls[0].headers


def test_himalayas_feed_uses_cursor_and_limit():
    router = Router().add(H, jr(fixture("himalayas_feed.json")))
    jobs = list(himalayas(router).list_jobs(SourceTarget(mode="feed")))
    assert len(jobs) == 1 and router.calls[0].url.params["limit"] == "20"


def test_himalayas_backs_off_on_rate_limit():
    sleeps: list = []
    router = Router().add(
        f"{H}/search",
        [
            httpx.Response(429, headers={"retry-after": "3"}),
            jr(fixture("himalayas_search_p2.json")),
        ],
    )
    jobs = list(himalayas(router, sleeps=sleeps).list_jobs(SourceTarget()))
    assert len(jobs) == 3 and sleeps == [3.0]


def test_himalayas_is_open_410_means_closed():
    router = (
        Router()
        .add(f"{H}/companies/acme-labs/jobs/gone", httpx.Response(410))
        .add(f"{H}/companies/acme-labs/jobs/live", jr({"ok": 1}))
    )
    src = himalayas(router)
    assert src.is_open("acme-labs/gone") is False
    assert src.is_open("acme-labs/live") is True


def test_himalayas_is_open_propagates_server_errors():
    from app.discovery.http import HttpStatus

    router = Router().add(f"{H}/companies/", httpx.Response(500))
    with pytest.raises(HttpStatus):
        himalayas(router).is_open("a/b")


# --- greenhouse -----------------------------------------------------------------
GH = "https://boards-api.greenhouse.io/v1/boards"


def test_greenhouse_lists_jobs_with_content():
    router = Router().add(f"{GH}/acme/jobs", jr(fixture("greenhouse_board.json")))
    jobs = list(
        GreenhouseSource(make_fetcher(router)).list_jobs(SourceTarget(token="acme"))
    )
    assert router.calls[0].url.params["content"] == "true"
    assert [j.external_id for j in jobs] == ["4001", "4002"]
    assert jobs[0].apply_url.endswith("/4001") and "Postgres" in jobs[0].raw_text
    assert "<p>" not in jobs[0].raw_text and jobs[1].remote and not jobs[0].remote


def test_greenhouse_404_and_empty_mark_the_board_gone():
    src = lambda r: GreenhouseSource(make_fetcher(r))
    with pytest.raises(BoardGone):
        list(src(Router()).list_jobs(SourceTarget(token="acme")))  # router default 404
    with pytest.raises(BoardGone):
        list(
            src(Router().add(GH, jr({"jobs": []}))).list_jobs(
                SourceTarget(token="acme")
            )
        )


def test_greenhouse_is_open():
    router = (
        Router()
        .add(f"{GH}/acme/jobs/1", jr({}))
        .add(f"{GH}/acme/jobs/2", httpx.Response(404))
    )
    src = GreenhouseSource(make_fetcher(router), "acme")
    assert src.is_open("1") and not src.is_open("2")


# --- lever / ashby ----------------------------------------------------------------
def test_lever_postings():
    router = Router().add(
        "https://api.lever.co/v0/postings/beta", jr(fixture("lever_postings.json"))
    )
    jobs = list(LeverSource(make_fetcher(router)).list_jobs(SourceTarget(token="beta")))
    assert [j.external_id for j in jobs] == ["aaaa-1111", "aaaa-2222"]
    assert jobs[0].apply_url == "https://jobs.lever.co/beta/aaaa-1111"
    assert "Kubernetes" in jobs[0].raw_text and not jobs[0].remote and jobs[1].remote


def test_lever_404_and_is_open():
    with pytest.raises(BoardGone):
        list(LeverSource(make_fetcher(Router())).list_jobs(SourceTarget(token="beta")))
    router = Router().add(
        "https://api.lever.co/v0/postings/beta/x1", httpx.Response(404)
    )
    assert LeverSource(make_fetcher(router), "beta").is_open("x1") is False


def test_ashby_skips_unlisted_and_checks_open():
    router = Router().add(
        "https://api.ashbyhq.com/posting-api/job-board/gamma",
        jr(fixture("ashby_board.json")),
    )
    src = AshbySource(make_fetcher(router), "gamma")
    jobs = list(src.list_jobs(SourceTarget(token="gamma")))
    assert [j.external_id for j in jobs] == ["b1"]
    assert jobs[0].apply_url.endswith("/application")
    assert src.is_open("b1") and not src.is_open("b2") and not src.is_open("zzz")
