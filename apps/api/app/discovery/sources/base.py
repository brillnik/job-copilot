import html
import re
from collections.abc import Iterator
from dataclasses import dataclass, field
from typing import Any, Protocol

from app.core.config import settings


@dataclass(frozen=True)
class SourceTarget:
    """What to list: a company board (token) or a Himalayas query."""

    token: str | None = None
    query: str | None = None
    country: str | None = None
    mode: str = "search"  # himalayas: search | feed


@dataclass
class RawJob:
    source: str
    external_id: str
    title: str
    apply_url: str
    raw_text: str
    location: str | None = None
    remote: bool = False
    country_restrictions: list[str] = field(default_factory=list)
    source_attribution: dict[str, Any] | None = None
    company_name: str | None = None
    company_key: str | None = None  # stable per-source company id (Himalayas slug)


class BoardGone(Exception):
    """The company board 404s or is empty: re-run ATS detection."""


class JobSource(Protocol):
    name: str

    def list_jobs(self, target: SourceTarget) -> Iterator[RawJob]: ...

    def is_open(self, external_id: str) -> bool: ...


def city_of(location: str | None) -> str | None:
    """First configured city mentioned in a free-text location, else None."""
    if not location:
        return None
    low = location.lower()
    for c in settings.allowed_cities:
        if c != "Remote" and c.lower() in low:
            return c
    return None


def is_remote_text(location: str | None) -> bool:
    return bool(location and "remote" in location.lower())


def strip_html(markup: str) -> str:
    text = re.sub(
        r"<(br|/p|/li|/h\d|/div)\s*/?>", "\n", markup or "", flags=re.IGNORECASE
    )
    text = html.unescape(re.sub(r"<[^>]+>", " ", text))
    text = re.sub(r"[ \t]+", " ", text)
    return re.sub(r"\n\s*\n+", "\n\n", text).strip()
