from collections.abc import Iterator

from app.discovery.http import Fetcher, HttpStatus
from app.discovery.sources.base import (
    BoardGone,
    RawJob,
    SourceTarget,
    is_remote_text,
    strip_html,
)

API = "https://api.lever.co/v0/postings"


class LeverSource:
    name = "lever"

    def __init__(self, http: Fetcher, token: str | None = None) -> None:
        self.http, self.token = http, token

    def list_jobs(self, target: SourceTarget) -> Iterator[RawJob]:
        token = target.token or self.token
        try:
            jobs = self.http.get_json(f"{API}/{token}", params={"mode": "json"})
        except HttpStatus as e:
            if e.status == 404:
                raise BoardGone(token) from None
            raise
        if not isinstance(jobs, list) or not jobs:
            raise BoardGone(token)
        for j in jobs:
            url = j.get("hostedUrl") or j.get("applyUrl")
            if not url or not j.get("text"):
                continue
            cats = j.get("categories") or {}
            loc = cats.get("location")
            lists = "\n".join(
                f"{x.get('text', '')}\n{strip_html(x.get('content', ''))}"
                for x in j.get("lists") or []
            )
            body = "\n".join(
                x
                for x in (
                    j.get("descriptionPlain"),
                    lists,
                    j.get("additionalPlain"),
                )
                if x
            )
            yield RawJob(
                source=self.name,
                external_id=j["id"],
                title=j["text"],
                apply_url=url,
                raw_text="\n".join(x for x in (j["text"], loc, body) if x),
                location=loc,
                remote=j.get("workplaceType") == "remote" or is_remote_text(loc),
            )

    def is_open(self, external_id: str) -> bool:
        try:
            self.http.get(f"{API}/{self.token}/{external_id}")
        except HttpStatus as e:
            if e.status in (404, 410):
                return False
            raise
        return True
