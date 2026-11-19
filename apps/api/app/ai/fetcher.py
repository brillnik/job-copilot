import html
import ipaddress
import re
import socket
from collections.abc import Callable
from typing import Any, Protocol
from urllib.parse import quote, urljoin, urlparse

import httpx
import trafilatura

from app.ai.errors import TransientError


class FetchError(Exception):
    """The posting cannot be fetched automatically; the user should paste it."""


class BlockedURL(FetchError):
    pass


class JobTextFetcher(Protocol):
    def fetch(self, url: str) -> str: ...


def is_login_walled(url: str, domains: list[str]) -> bool:
    host = (urlparse(url).hostname or "").lower()
    return any(host == d or host.endswith(f".{d}") for d in domains)


def _is_public(ip: ipaddress._BaseAddress) -> bool:
    if isinstance(ip, ipaddress.IPv6Address) and ip.ipv4_mapped:
        ip = ip.ipv4_mapped
    return ip.is_global and not ip.is_multicast


def assert_public_url(
    url: str,
    resolve: Callable[..., Any] = socket.getaddrinfo,
) -> None:
    """Reject anything that could reach internal infrastructure (SSRF).

    Every address the host resolves to must be public, so a name that also points
    at 127.0.0.1 or 169.254.169.254 is refused. Called for every redirect hop.
    """
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https"):
        raise BlockedURL("Only http(s) links are supported")
    host = parsed.hostname
    if not host:
        raise BlockedURL("Link has no host")
    try:
        infos = resolve(host, parsed.port or (443 if parsed.scheme == "https" else 80))
    except OSError as e:
        raise FetchError("Could not resolve the link's host") from e
    for info in infos:
        ip = ipaddress.ip_address(info[4][0].split("%")[0])
        if not _is_public(ip):
            raise BlockedURL("Link points to a non-public address")


# --- ATS public job JSON ---------------------------------------------------
_SLUG = r"[\w.-]+"


def ats_api_url(url: str) -> tuple[str, str, str] | None:
    """(kind, api_url, job_id) for Greenhouse / Lever / Ashby posting links."""
    p = urlparse(url)
    host = (p.hostname or "").lower()
    parts = [x for x in p.path.split("/") if x]
    if host.endswith("greenhouse.io") and len(parts) >= 3 and parts[1] == "jobs":
        company, job = parts[0], parts[2]
        if re.fullmatch(_SLUG, company) and job.isdigit():
            return (
                "greenhouse",
                f"https://boards-api.greenhouse.io/v1/boards/{quote(company)}/jobs/{job}",
                job,
            )
    if host == "jobs.lever.co" and len(parts) >= 2:
        company, job = parts[0], parts[1]
        if re.fullmatch(_SLUG, company) and re.fullmatch(r"[\w-]+", job):
            return (
                "lever",
                f"https://api.lever.co/v0/postings/{quote(company)}/{quote(job)}",
                job,
            )
    if host == "jobs.ashbyhq.com" and len(parts) >= 2:
        company, job = parts[0], parts[1]
        if re.fullmatch(_SLUG, company) and re.fullmatch(r"[\w-]+", job):
            return (
                "ashby",
                f"https://api.ashbyhq.com/posting-api/job-board/{quote(company)}",
                job,
            )
    return None


def html_to_text(markup: str) -> str:
    """Text of an HTML fragment (ATS APIs return fragments, not whole pages)."""
    if not markup.strip():
        return ""
    text = trafilatura.html2txt(f"<html><body>{markup}</body></html>")
    if text and text.strip():
        return text
    # Last resort: keep the words even if the parser gave up.
    return html.unescape(re.sub(r"<[^>]+>", " ", markup))


def ats_text(kind: str, data: dict, job_id: str) -> str:
    """Flatten an ATS posting JSON into text."""
    if kind == "greenhouse":
        loc = (data.get("location") or {}).get("name")
        body = html_to_text(html.unescape(data.get("content", "")))
        return "\n".join(x for x in (data.get("title"), loc, body) if x)
    if kind == "lever":
        cats = data.get("categories") or {}
        lists = "\n".join(
            f"{x.get('text', '')}\n{html_to_text(x.get('content', ''))}"
            for x in data.get("lists", [])
        )
        return "\n".join(
            x
            for x in (
                data.get("text"),
                cats.get("location"),
                cats.get("commitment"),
                data.get("descriptionPlain"),
                lists,
                data.get("additionalPlain"),
            )
            if x
        )
    if kind == "ashby":
        job = next((j for j in data.get("jobs", []) if j.get("id") == job_id), None)
        if job is None:
            raise FetchError("Posting not found on the job board")
        return "\n".join(
            x
            for x in (
                job.get("title"),
                job.get("location"),
                job.get("descriptionPlain"),
            )
            if x
        )
    raise FetchError("Unknown job board")


class HttpJobFetcher:
    def __init__(
        self,
        timeout: float,
        max_bytes: int,
        max_redirects: int,
        client: httpx.Client | None = None,
        resolve: Callable[..., Any] = socket.getaddrinfo,
    ) -> None:
        self.timeout = timeout
        self.max_bytes = max_bytes
        self.max_redirects = max_redirects
        self.resolve = resolve
        # Redirects are followed by hand so each hop can be checked.
        self.client = client or httpx.Client(timeout=timeout, follow_redirects=False)

    def fetch(self, url: str) -> str:
        ats = ats_api_url(url)
        if ats:
            kind, api_url, job_id = ats
            body = self._get(api_url)
            try:
                import json

                return ats_text(kind, json.loads(body), job_id)
            except ValueError as e:
                raise FetchError("Job board returned an unreadable response") from e
        page = self._get(url).decode("utf-8", "replace")
        return trafilatura.extract(page) or ""

    def _get(self, url: str) -> bytes:
        for _ in range(self.max_redirects + 1):
            assert_public_url(url, self.resolve)
            try:
                with self.client.stream(
                    "GET", url, headers={"User-Agent": "JobCopilot/1.0"}
                ) as r:
                    if r.is_redirect and (loc := r.headers.get("location")):
                        url = urljoin(url, loc)
                        continue
                    if r.status_code in (429, 500, 502, 503, 504):
                        raise TransientError(f"http {r.status_code}")
                    if r.status_code >= 400:
                        raise FetchError(f"The site answered {r.status_code}")
                    buf = bytearray()
                    for chunk in r.iter_bytes():
                        buf += chunk
                        if len(buf) >= self.max_bytes:
                            break
                    return bytes(buf[: self.max_bytes])
            except httpx.TimeoutException as e:
                raise TransientError("timeout") from e
            except httpx.TransportError as e:
                raise TransientError("network") from e
        raise FetchError("Too many redirects")
