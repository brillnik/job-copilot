"""Fakes and factories for the discovery tests. No network, no LLM."""

import json
from datetime import UTC, datetime
from pathlib import Path

import httpx

from app.ai.embeddings import HashingEmbedder
from app.core.netguard import guarded_client
from app.discovery.detector import AtsDetector
from app.discovery.http import Fetcher
from app.discovery.pipeline import DiscoveryContext, company_for, embed_text
from app.models.discovery import CatalogJob, Company
from app.repositories.manager import RepositoryManager
from app.schemas.job import JobDescription
from tests.jobs_helpers import FakeExtractor, make_ctx

FIX = Path(__file__).parent / "fixtures" / "discovery"
NOW = datetime(2026, 11, 19, 6, 0, tzinfo=UTC)


def fixture(name: str):
    text = (FIX / name).read_text()
    return json.loads(text) if name.endswith(".json") else text


class Router:
    """httpx MockTransport handler: (method-less) URL prefix -> response factory."""

    def __init__(self):
        self.routes: list[tuple[str, object]] = []
        self.calls: list[httpx.Request] = []

    def add(self, prefix: str, response):
        self.routes.append((prefix, response))
        return self

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.calls.append(request)
        url = str(request.url)
        for prefix, resp in self.routes:
            if url.startswith(prefix):
                r = resp(request) if callable(resp) else resp
                if isinstance(r, list):  # sequence of responses
                    r = r.pop(0) if len(r) > 1 else r[0]
                return r
        return httpx.Response(404)

    def urls(self) -> list[str]:
        return [str(c.url) for c in self.calls]


def jr(data, status=200, headers=None):
    return httpx.Response(status, json=data, headers=headers)


def make_fetcher(router: Router, sleeps: list | None = None, **kw) -> Fetcher:
    client = guarded_client(
        transport=httpx.MockTransport(router), follow_redirects=True
    )
    sleeps = sleeps if sleeps is not None else []
    return Fetcher(
        client, sleep=sleeps.append, retries=3, backoff_s=1.0, per_host=2, **kw
    )


def public_resolve(host, port):
    return [(2, 1, 6, "", ("93.184.216.34", port))]


def make_dctx(db, tmp_path, router: Router | None = None, extractor=None, **over):
    router = router or Router()
    task = make_ctx(db, tmp_path, extractor=extractor or FakeExtractor(), **over)
    client = guarded_client(transport=httpx.MockTransport(router))
    dctx = DiscoveryContext(
        task=task,
        http=Fetcher(client, sleep=lambda s: None, retries=1, backoff_s=0, per_host=2),
        detector=AtsDetector(client, resolve=public_resolve),
        now=lambda: NOW,
        workers=1,
    )
    dctx.extra["router"] = router
    return dctx


def jd_for(
    title="Backend Engineer", must=("Python", "Postgres"), **kw
) -> JobDescription:
    return JobDescription(
        title=title,
        company="Acme",
        location="Bengaluru",
        must_have=list(must),
        responsibilities=["Build APIs"],
        **kw,
    )


def make_catalog(
    db,
    *,
    title="Backend Engineer",
    external_id=None,
    source="greenhouse",
    company="Acme",
    jd: JobDescription | None = None,
    remote=False,
    city="Bengaluru",
    restrictions=(),
    first_seen=NOW,
    closed_at=None,
    embed=True,
    duplicate_of=None,
) -> CatalogJob:
    repos = RepositoryManager(db)
    co = company_for(repos, company)
    jd = jd or jd_for(title)
    emb = HashingEmbedder()
    row = CatalogJob(
        source=source,
        external_id=external_id or f"{title}-{company}",
        company_id=co.id,
        title=title,
        location=city,
        city=city,
        remote=remote,
        country_restrictions=list(restrictions),
        apply_url=f"https://example.com/apply/{title.replace(' ', '-')}?ref=x",
        source_attribution={"provider": "Himalayas"} if source == "himalayas" else None,
        raw_text=f"{title}\n{jd.must_have}",
        content_hash=f"h-{title}-{company}-{external_id}",
        jd=jd.model_dump(mode="json"),
        embedding=emb.embed_documents([embed_text(jd, title)])[0] if embed else None,
        embedding_model=emb.name if embed else None,
        first_seen=first_seen,
        last_seen=first_seen,
        closed_at=closed_at,
        duplicate_of=duplicate_of,
    )
    db.add(row)
    db.commit()
    return row


__all__ = ["Company"]
