"""Himalayas public API. Attribution is kept and apply_url is always the
applicationLink. Catalogue data is never exported or syndicated."""

import logging
import re
from collections.abc import Iterator
from typing import Any

from app.core.config import settings
from app.discovery.http import Fetcher, HttpStatus
from app.discovery.sources.base import (
    RawJob,
    SourceTarget,
    is_remote_text,
    strip_html,
)

log = logging.getLogger(__name__)
PAGE = 20
_GUID = re.compile(r"/companies/([^/]+)/jobs/([^/?#]+)")


class HimalayasSource:
    name = "himalayas"

    def __init__(self, http: Fetcher, base_url: str | None = None) -> None:
        self.http = http
        self.base = (base_url or settings.himalayas_base_url).rstrip("/")

    def _headers(self) -> dict[str, str] | None:
        key = settings.himalayas_api_key
        return {"Authorization": f"Bearer {key}"} if key else None

    def _get(self, path: str, params: dict[str, Any]) -> dict:
        return self.http.get_json(
            f"{self.base}{path}", params=params, headers=self._headers()
        )

    def list_jobs(self, target: SourceTarget) -> Iterator[RawJob]:
        if target.mode == "feed":
            yield from self._feed()
        else:
            yield from self._search(target)

    def _search(self, t: SourceTarget) -> Iterator[RawJob]:
        for page in range(1, settings.discovery_max_pages + 1):
            params: dict[str, Any] = {"page": page}
            if t.query:
                params["q"] = t.query
            if t.country:
                params["country"] = t.country
            jobs = self._get("/jobs/api/search", params).get("jobs") or []
            for j in jobs:
                if (raw := self._raw(j)) is not None:
                    yield raw
            if len(jobs) < PAGE:
                return

    def _feed(self) -> Iterator[RawJob]:
        cursor = None
        for _ in range(settings.discovery_max_pages):
            params: dict[str, Any] = {"limit": PAGE}
            if cursor:
                params["cursor"] = cursor
            data = self._get("/jobs/api", params)
            jobs = data.get("jobs") or []
            for j in jobs:
                if (raw := self._raw(j)) is not None:
                    yield raw
            cursor = data.get("nextCursor") or data.get("cursor")
            if not cursor or not jobs:
                return

    def _raw(self, j: dict) -> RawJob | None:
        link = j.get("applicationLink")
        title = j.get("title")
        if not link or not title:
            return None
        guid = j.get("guid") or link
        m = _GUID.search(guid)
        company_key = j.get("companySlug") or (m.group(1) if m else None)
        ext = f"{m.group(1)}/{m.group(2)}" if m else guid
        restrictions = [str(x) for x in j.get("locationRestrictions") or []]
        loc = ", ".join(restrictions) if restrictions else "Remote"
        text = strip_html(j.get("description") or j.get("excerpt") or "")
        return RawJob(
            source=self.name,
            external_id=ext,
            title=title,
            apply_url=link,
            raw_text="\n".join(x for x in (title, loc, text) if x),
            location=loc,
            remote=True,  # Himalayas lists remote roles only
            country_restrictions=restrictions,
            source_attribution={
                "provider": "Himalayas",
                "url": guid,
                "company": j.get("companyName"),
                "logo": j.get("companyLogo"),
            },
            company_name=j.get("companyName"),
            company_key=company_key,
        )

    def is_open(self, external_id: str) -> bool:
        company, _, slug = external_id.partition("/")
        if not slug:
            return True  # cannot check; the sweep keeps it until it is seen again
        try:
            self.http.get(
                f"{self.base}/jobs/api/companies/{company}/jobs/{slug}",
                headers=self._headers(),
            )
        except HttpStatus as e:
            if e.status in (404, 410):
                return False
            raise
        return True


__all__ = ["HimalayasSource", "is_remote_text"]
