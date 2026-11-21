from collections.abc import Iterator

from app.discovery.http import Fetcher, HttpStatus
from app.discovery.sources.base import (
    BoardGone,
    RawJob,
    SourceTarget,
    is_remote_text,
    strip_html,
)

API = "https://api.ashbyhq.com/posting-api/job-board"


class AshbySource:
    name = "ashby"

    def __init__(self, http: Fetcher, token: str | None = None) -> None:
        self.http, self.token = http, token

    def _board(self, token: str | None) -> list[dict]:
        try:
            data = self.http.get_json(f"{API}/{token}")
        except HttpStatus as e:
            if e.status == 404:
                raise BoardGone(token) from None
            raise
        return [j for j in data.get("jobs") or [] if j.get("isListed", True)]

    def list_jobs(self, target: SourceTarget) -> Iterator[RawJob]:
        jobs = self._board(target.token or self.token)
        if not jobs:
            raise BoardGone(target.token or self.token)
        for j in jobs:
            url = j.get("applyUrl") or j.get("jobUrl")
            if not url or not j.get("title"):
                continue
            loc = j.get("location")
            body = j.get("descriptionPlain") or strip_html(
                j.get("descriptionHtml") or ""
            )
            yield RawJob(
                source=self.name,
                external_id=j["id"],
                title=j["title"],
                apply_url=url,
                raw_text="\n".join(x for x in (j["title"], loc, body) if x),
                location=loc,
                remote=bool(j.get("isRemote")) or is_remote_text(loc),
            )

    def is_open(self, external_id: str) -> bool:
        return any(j.get("id") == external_id for j in self._board(self.token))
