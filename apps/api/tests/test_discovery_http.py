import httpx
import pytest

from app.ai.fetcher import BlockedURL, HttpJobFetcher
from app.core.netguard import DeniedHost, guarded_client, is_denied
from app.discovery.http import HttpStatus
from tests.discovery_helpers import Router, jr, make_fetcher, public_resolve


@pytest.mark.parametrize(
    "url",
    [
        "https://wellfound.com/jobs/1",
        "https://www.naukri.com/job-listings-x",
        "https://hiring.cafe/jobs",
        "https://linkedin.com/jobs/view/1",
        "https://in.linkedin.com/jobs/view/1",
        "https://WWW.LinkedIn.com./jobs",
    ],
)
def test_denied_hosts(url):
    assert is_denied(url)


@pytest.mark.parametrize(
    "url",
    [
        "https://boards.greenhouse.io/acme",
        "https://notlinkedin.com/x",
        "https://x.co/linkedin.com",
    ],
)
def test_allowed_hosts(url):
    assert not is_denied(url)


def test_guarded_client_never_sends_a_denied_request():
    router = Router()
    c = guarded_client(transport=httpx.MockTransport(router))
    with pytest.raises(DeniedHost):
        c.get("https://www.linkedin.com/jobs/view/123")
    assert router.calls == []


def test_redirect_into_a_denied_host_is_refused():
    router = Router().add(
        "https://good.example/",
        httpx.Response(302, headers={"location": "https://www.naukri.com/x"}),
    )
    c = guarded_client(transport=httpx.MockTransport(router), follow_redirects=True)
    with pytest.raises(DeniedHost):
        c.get("https://good.example/start")
    assert router.urls() == ["https://good.example/start"]


def test_discovery_fetcher_uses_the_deny_list():
    router = Router()
    f = make_fetcher(router)
    with pytest.raises(DeniedHost):
        f.get("https://wellfound.com/company/x")
    assert router.calls == []


def test_v1_job_fetcher_refuses_denied_hosts():
    router = Router()
    client = httpx.Client(transport=httpx.MockTransport(router))
    fetcher = HttpJobFetcher(5, 10_000, 3, client=client, resolve=public_resolve)
    for url in ("https://hiring.cafe/jobs/1", "https://uk.linkedin.com/jobs/1"):
        with pytest.raises(BlockedURL):
            fetcher.fetch(url)
    assert router.calls == []


# --- backoff -----------------------------------------------------------------
def test_backoff_on_429_honours_retry_after_then_succeeds():
    sleeps: list = []
    router = Router().add(
        "https://api.test/x",
        [
            httpx.Response(429, headers={"retry-after": "7"}),
            httpx.Response(503),
            jr({"ok": 1}),
        ],
    )
    f = make_fetcher(router, sleeps)
    assert f.get_json("https://api.test/x") == {"ok": 1}
    assert sleeps == [7.0, 2.0]  # Retry-After wins over 1s; then exponential 2s


def test_retries_exhausted_raises_with_last_status():
    sleeps: list = []
    router = Router().add("https://api.test/x", httpx.Response(500))
    f = make_fetcher(router, sleeps)
    with pytest.raises(HttpStatus) as e:
        f.get("https://api.test/x")
    assert e.value.status == 500 and len(router.calls) == 4 and len(sleeps) == 3


@pytest.mark.parametrize("status", [404, 410, 403])
def test_client_errors_are_not_retried(status):
    router = Router().add("https://api.test/x", httpx.Response(status))
    f = make_fetcher(router)
    with pytest.raises(HttpStatus) as e:
        f.get("https://api.test/x")
    assert e.value.status == status and len(router.calls) == 1
