"""ATS detection from a careers page: robots.txt honoured, SSRF-safe, 10 s timeout."""

import logging
import re
from collections.abc import Callable
from typing import Any
from urllib.parse import urljoin, urlparse
from urllib.robotparser import RobotFileParser

import httpx

from app.ai.fetcher import BlockedURL, FetchError, assert_public_url
from app.core.config import settings
from app.core.netguard import DeniedHost, assert_allowed, guarded_client

log = logging.getLogger(__name__)

_TOKEN = r"([A-Za-z0-9][A-Za-z0-9_.-]*)"
# (ats, pattern); the first match wins. Embed scripts/iframes are covered by the
# same URL shapes (e.g. boards.greenhouse.io/embed/job_board?for=<token>).
PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    ("greenhouse", re.compile(r"job-boards\.(?:eu\.)?greenhouse\.io/" + _TOKEN)),
    (
        "greenhouse",
        re.compile(r"boards\.greenhouse\.io/embed/job_board[^\"'\s]*[?&]for=" + _TOKEN),
    ),
    ("greenhouse", re.compile(r"boards\.greenhouse\.io/" + _TOKEN)),
    ("lever", re.compile(r"jobs\.(?:eu\.)?lever\.co/" + _TOKEN)),
    ("ashby", re.compile(r"jobs\.ashbyhq\.com/" + _TOKEN)),
]
_RESERVED = {"embed", "v1", "js", "static", "assets", "api"}


def detect_in_html(markup: str) -> tuple[str, str] | None:
    for ats, pat in PATTERNS:
        for m in pat.finditer(markup):
            token = m.group(1)
            if token.lower() not in _RESERVED:
                return ats, token
    return None


class AtsDetector:
    def __init__(
        self,
        client: httpx.Client | None = None,
        resolve: Callable[..., Any] | None = None,
    ) -> None:
        # Redirects are followed by hand so every hop is checked.
        self.client = client or guarded_client(
            timeout=settings.discovery_http_timeout_s,
            headers={"User-Agent": settings.discovery_user_agent},
        )
        self.resolve = resolve
        self.max_bytes = settings.fetch_max_bytes

    def _check(self, url: str) -> None:
        assert_allowed(url)
        if self.resolve is None:
            assert_public_url(url)
        else:
            assert_public_url(url, self.resolve)

    def _get(self, url: str) -> httpx.Response | None:
        for _ in range(settings.fetch_max_redirects + 1):
            self._check(url)
            r = self.client.get(url)
            if r.is_redirect and (loc := r.headers.get("location")):
                url = urljoin(url, loc)
                continue
            return r
        raise FetchError("Too many redirects")

    def allowed_by_robots(self, url: str) -> bool:
        p = urlparse(url)
        robots = f"{p.scheme}://{p.netloc}/robots.txt"
        try:
            r = self._get(robots)
        except (FetchError, httpx.HTTPError):
            return True  # unreachable robots.txt: no rules to honour
        if r is None or r.status_code >= 500:
            return False  # RFC 9309: server error means do not crawl
        if r.status_code >= 400:
            return True
        rp = RobotFileParser()
        rp.parse(r.text.splitlines())
        return rp.can_fetch(settings.discovery_user_agent.split("/")[0], url)

    def detect(self, careers_url: str) -> tuple[str, str] | None:
        """(ats, board_token) or None. Never raises for an unreachable site."""
        try:
            if not self.allowed_by_robots(careers_url):
                log.info(
                    "ats detect skipped by robots host=%s",
                    urlparse(careers_url).hostname,
                )
                return None
            r = self._get(careers_url)
        except (DeniedHost, BlockedURL, FetchError, httpx.HTTPError) as e:
            log.info("ats detect failed error=%s", type(e).__name__)
            return None
        if r is None or r.status_code >= 400:
            return None
        found = detect_in_html(r.text[: self.max_bytes])
        if found is None:  # the careers URL itself may already be a board link
            found = detect_in_html(str(r.url))
        return found
