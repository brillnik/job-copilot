"""Outbound deny-list: the server never fetches these sites (spec: Global rules)."""

from urllib.parse import urlparse

import httpx

DENIED_DOMAINS = ("wellfound.com", "naukri.com", "hiring.cafe", "linkedin.com")


class DeniedHost(Exception):
    """The URL points at a site the server must never fetch."""


def is_denied(url: str) -> bool:
    host = (urlparse(url).hostname or "").lower().rstrip(".")
    return any(host == d or host.endswith(f".{d}") for d in DENIED_DOMAINS)


def assert_allowed(url: str) -> None:
    if is_denied(url):
        raise DeniedHost("This site is not fetched by the server")


def _check_request(request: httpx.Request) -> None:
    assert_allowed(str(request.url))


def guarded_client(
    *,
    timeout: float = 10.0,
    transport: httpx.BaseTransport | None = None,
    headers: dict[str, str] | None = None,
    follow_redirects: bool = False,
) -> httpx.Client:
    """An httpx client that refuses deny-listed hosts on every request and redirect hop."""
    return httpx.Client(
        timeout=timeout,
        transport=transport,
        headers=headers,
        follow_redirects=follow_redirects,
        event_hooks={"request": [_check_request]},
    )
