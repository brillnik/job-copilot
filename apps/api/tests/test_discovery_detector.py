import httpx
import pytest

from app.core.netguard import guarded_client
from app.discovery.detector import AtsDetector, detect_in_html
from tests.discovery_helpers import Router, fixture, public_resolve


def detector(router, resolve=public_resolve):
    client = guarded_client(transport=httpx.MockTransport(router))
    return AtsDetector(client, resolve=resolve)


def html(name):
    return httpx.Response(200, text=fixture(name))


@pytest.mark.parametrize(
    ("name", "expected"),
    [
        ("careers_greenhouse.html", ("greenhouse", "acme")),  # embed script
        ("careers_greenhouse_new.html", ("greenhouse", "acmeco")),  # job-boards.
        ("careers_lever.html", ("lever", "beta")),
        ("careers_ashby.html", ("ashby", "gamma")),
        ("careers_none.html", None),
    ],
)
def test_detect_in_saved_html(name, expected):
    assert detect_in_html(fixture(name)) == expected


def test_detect_fetches_page_and_returns_ats():
    router = (
        Router()
        .add("https://acme.test/robots.txt", httpx.Response(404))
        .add("https://acme.test/careers", html("careers_lever.html"))
    )
    assert detector(router).detect("https://acme.test/careers") == ("lever", "beta")


def test_robots_disallow_is_honoured():
    router = (
        Router()
        .add(
            "https://acme.test/robots.txt",
            httpx.Response(200, text=fixture("robots_disallow.txt")),
        )
        .add("https://acme.test/careers", html("careers_lever.html"))
    )
    assert detector(router).detect("https://acme.test/careers") is None
    assert router.urls() == ["https://acme.test/robots.txt"]  # page never requested


def test_robots_allows_other_paths_and_sends_user_agent():
    router = (
        Router()
        .add(
            "https://acme.test/robots.txt",
            httpx.Response(200, text=fixture("robots_allow.txt")),
        )
        .add("https://acme.test/careers", html("careers_ashby.html"))
    )
    client = guarded_client(
        transport=httpx.MockTransport(router),
        headers={"User-Agent": "JobCopilotBot/1.0"},
    )
    d = AtsDetector(client, resolve=public_resolve)
    assert d.detect("https://acme.test/careers") == ("ashby", "gamma")
    assert "JobCopilotBot" in router.calls[-1].headers["user-agent"]


def test_ssrf_private_address_is_never_requested():
    router = Router().add("http://", html("careers_lever.html"))
    private = lambda host, port: [(2, 1, 6, "", ("127.0.0.1", port))]
    assert (
        detector(router, resolve=private).detect("http://internal.test/careers") is None
    )
    assert router.calls == []


def test_redirect_to_private_address_is_blocked():
    def resolve(host, port):
        ip = "10.0.0.5" if host == "evil.test" else "93.184.216.34"
        return [(2, 1, 6, "", (ip, port))]

    router = (
        Router()
        .add("https://acme.test/robots.txt", httpx.Response(404))
        .add(
            "https://acme.test/careers",
            httpx.Response(302, headers={"location": "https://evil.test/x"}),
        )
    )
    assert detector(router, resolve).detect("https://acme.test/careers") is None
    assert not any("evil.test" in u for u in router.urls())


def test_denied_careers_url_is_not_fetched():
    router = Router()
    assert detector(router).detect("https://www.linkedin.com/company/acme/jobs") is None
    assert router.calls == []


def test_unreachable_site_returns_none():
    def boom(request):
        raise httpx.ConnectError("down")

    assert (
        detector(Router().add("https://", boom)).detect("https://acme.test/careers")
        is None
    )
