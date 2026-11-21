import html
from collections.abc import Iterator

from app.discovery.http import Fetcher, HttpStatus
from app.discovery.sources.base import (
    BoardGone,
    RawJob,
    SourceTarget,
    is_remote_text,
    strip_html,
)

API = "https://boards-api.greenhouse.io/v1/boards"


class GreenhouseSource:
    name = "greenhouse"

    def __init__(self, http: Fetcher, token: str | None = None) -> None:
        self.http, self.token = http, token

    def list_jobs(self, target: SourceTarget) -> Iterator[RawJob]:
        token = target.token or self.token
        try:
            data = self.http.get_json(f"{API}/{token}/jobs", params={"content": "true"})
        except HttpStatus as e:
            if e.status == 404:
                raise BoardGone(token) from None
            raise
        jobs = data.get("jobs") or []
        if not jobs:
            raise BoardGone(token)
        for j in jobs:
            if not j.get("absolute_url") or not j.get("title"):
                continue
            loc = (j.get("location") or {}).get("name")
            body = strip_html(html.unescape(j.get("content") or ""))
            yield RawJob(
                source=self.name,
                external_id=str(j["id"]),
                title=j["title"],
                apply_url=j["absolute_url"],
                raw_text="\n".join(x for x in (j["title"], loc, body) if x),
                location=loc,
                remote=is_remote_text(loc),
            )

    def is_open(self, external_id: str) -> bool:
        try:
            self.http.get(f"{API}/{self.token}/jobs/{external_id}")
        except HttpStatus as e:
            if e.status in (404, 410):
                return False
            raise
        return True
