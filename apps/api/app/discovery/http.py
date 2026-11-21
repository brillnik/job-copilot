"""HTTP for discovery: deny-listed client, per-host concurrency limit, backoff.

Every discovery fetch goes through Fetcher; it can never reach a deny-listed host.
"""

import logging
import threading
import time
from collections.abc import Callable
from typing import Any
from urllib.parse import urlparse

import httpx

from app.core.config import settings
from app.core.netguard import DeniedHost, guarded_client

log = logging.getLogger(__name__)


class HttpStatus(Exception):
    """A non-retryable HTTP status (404, 410, other 4xx) or retries exhausted."""

    def __init__(self, status: int) -> None:
        self.status = status
        super().__init__(f"http {status}")


class Fetcher:
    def __init__(
        self,
        client: httpx.Client | None = None,
        *,
        sleep: Callable[[float], None] = time.sleep,
        retries: int | None = None,
        backoff_s: float | None = None,
        per_host: int | None = None,
    ) -> None:
        self.client = client or guarded_client(
            timeout=settings.discovery_http_timeout_s,
            headers={"User-Agent": settings.discovery_user_agent},
            follow_redirects=True,
        )
        self.sleep = sleep
        self.retries = settings.discovery_max_retries if retries is None else retries
        self.backoff_s = (
            settings.discovery_backoff_s if backoff_s is None else backoff_s
        )
        self._limit = per_host or settings.discovery_host_concurrency
        self._sems: dict[str, threading.BoundedSemaphore] = {}
        self._lock = threading.Lock()

    def _sem(self, host: str) -> threading.BoundedSemaphore:
        with self._lock:
            return self._sems.setdefault(host, threading.BoundedSemaphore(self._limit))

    def get(
        self,
        url: str,
        *,
        params: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
    ) -> httpx.Response:
        """GET with backoff on 429/5xx/network errors (honours Retry-After).

        Raises HttpStatus for 4xx (and exhausted retries) and DeniedHost for
        deny-listed sites. Redirects are followed by the client hop by hop.
        """
        host = (urlparse(url).hostname or "").lower()
        last: int | str = 0
        for attempt in range(self.retries + 1):
            try:
                with self._sem(host):
                    r = self.client.get(url, params=params, headers=headers)
            except DeniedHost:
                raise
            except httpx.TransportError as e:
                last = type(e).__name__
                log.warning("discovery fetch error host=%s error=%s", host, last)
                delay = self.backoff_s * 2**attempt
            else:
                if r.status_code < 400:
                    return r
                if r.status_code not in (429, 500, 502, 503, 504):
                    raise HttpStatus(r.status_code)
                last = r.status_code
                delay = self.backoff_s * 2**attempt
                ra = r.headers.get("retry-after", "")
                if ra.isdigit():
                    delay = max(delay, min(float(ra), 60.0))
                log.warning("discovery fetch retry host=%s status=%s", host, last)
            if attempt < self.retries:
                self.sleep(delay)
        raise HttpStatus(last if isinstance(last, int) and last else 599)

    def get_json(self, url: str, **kw: Any) -> Any:
        return self.get(url, **kw).json()
