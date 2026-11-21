"""Daily discovery pipeline steps. Logs carry ids and counts only, never posting text."""

import logging
import re
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.ai.errors import TransientError
from app.core.config import settings
from app.core.netguard import DeniedHost
from app.discovery.detector import AtsDetector
from app.discovery.http import Fetcher, HttpStatus
from app.discovery.lists_loader import name_key
from app.discovery.sources.ashby import AshbySource
from app.discovery.sources.base import (
    BoardGone,
    JobSource,
    RawJob,
    SourceTarget,
    city_of,
)
from app.discovery.sources.greenhouse import GreenhouseSource
from app.discovery.sources.himalayas import HimalayasSource
from app.discovery.sources.lever import LeverSource
from app.models.discovery import CatalogJob, Company
from app.models.profile import Profile
from app.models.user import User
from app.repositories.manager import RepositoryManager
from app.schemas.job import JobDescription
from app.tasks.jobs import TaskContext, content_hash

log = logging.getLogger(__name__)
HIMALAYAS = "himalayas"


def _utcnow() -> datetime:
    return datetime.now(UTC)


@dataclass
class DiscoveryContext:
    task: TaskContext  # session_factory, extractor, embedder, scoring, queue
    http: Fetcher
    detector: AtsDetector
    now: Callable[[], datetime] = _utcnow
    workers: int | None = None
    extra: dict[str, Any] = field(default_factory=dict)

    @property
    def session_factory(self):
        return self.task.session_factory


def build_source(name: str, http: Fetcher, token: str | None = None) -> JobSource:
    if name == HIMALAYAS:
        return HimalayasSource(http)
    cls = {"greenhouse": GreenhouseSource, "lever": LeverSource, "ashby": AshbySource}[
        name
    ]
    return cls(http, token)


# --- upsert -------------------------------------------------------------------
def company_for(repos: RepositoryManager, name: str) -> Company:
    key = name_key(name)
    row = repos.catalog.company_by_key(key)
    if row is None:
        row = Company(name=name, name_key=key, ats="unknown", lists=[])
        repos.session.add(row)
        repos.session.flush()
    return row


def upsert_raw(
    repos: RepositoryManager, company: Company, raw: RawJob, now: datetime
) -> bool:
    """Insert or refresh one posting; True when it is new or its text changed."""
    digest = content_hash(f"{raw.title}\n{raw.raw_text}")
    row = repos.catalog.get_job(raw.source, raw.external_id)
    fields = {
        "title": raw.title[:512],
        "location": raw.location,
        "city": city_of(raw.location),
        "remote": raw.remote,
        "country_restrictions": raw.country_restrictions,
        "apply_url": raw.apply_url,
        "source_attribution": raw.source_attribution,
    }
    if row is None:
        repos.session.add(
            CatalogJob(
                source=raw.source,
                external_id=raw.external_id,
                company_id=company.id,
                raw_text=raw.raw_text,
                content_hash=digest,
                first_seen=now,
                last_seen=now,
                **fields,
            )
        )
        return True
    for k, v in fields.items():
        setattr(row, k, v)
    row.last_seen, row.closed_at = now, None  # seen again: (re)open
    if row.content_hash == digest:
        return False
    row.raw_text, row.content_hash = raw.raw_text, digest
    row.jd = row.embedding = row.embedding_model = None  # re-extract once
    return True


def _sync_one(ctx: DiscoveryContext, company_id: str | None, source: str | None) -> int:
    """Fetch one source/company and upsert. Returns the number of postings seen."""
    seen = 0
    with ctx.session_factory() as session:
        repos = RepositoryManager(session)
        now = ctx.now()
        if company_id is None:
            adapter = build_source(source or HIMALAYAS, ctx.http)
            target = SourceTarget(
                query=settings.himalayas_query or None,
                country=settings.himalayas_country or None,
            )
            company = None
        else:
            company = repos.catalog.company(company_id)
            if company is None or company.ats == "unknown" or not company.board_token:
                log.info("sync_source skipped company=%s reason=no_board", company_id)
                return 0
            adapter = build_source(company.ats, ctx.http, company.board_token)
            target = SourceTarget(token=company.board_token)
        try:
            for raw in adapter.list_jobs(target):
                owner = company or company_for(
                    repos, raw.company_name or raw.company_key or "Unknown"
                )
                upsert_raw(repos, owner, raw, now)
                seen += 1
                if seen % 50 == 0:
                    session.commit()
        except BoardGone:
            session.rollback()
            if company is not None:
                company = repos.catalog.company(company_id)
                company.redetect = True
                session.commit()
            log.info("sync_source board gone company=%s", company_id)
            return seen
        except (HttpStatus, DeniedHost, TransientError) as e:
            log.warning(
                "sync_source stopped company=%s error=%s", company_id, type(e).__name__
            )
        session.commit()
    log.info("sync_source done company=%s source=%s seen=%d", company_id, source, seen)
    return seen


# --- enrich: extract once, embed -----------------------------------------------
def embed_text(jd: JobDescription, title: str) -> str:
    return "\n".join([jd.title or title, *jd.must_have, *jd.responsibilities])


def enrich(ctx: DiscoveryContext, limit: int | None = None) -> int:
    """Extract the JD once per new/changed posting and embed it. Shared, not per user."""
    limit = limit or settings.discovery_max_extractions_per_run
    embedder = ctx.task.embedder
    done = 0
    with ctx.session_factory() as session:
        repos = RepositoryManager(session)
        rows = repos.catalog.needing_enrichment(embedder.name, limit)
        for row in rows:
            if row.jd is None:
                twin = repos.catalog.by_content_hash(row.content_hash)
                if twin is not None and twin.id != row.id:
                    row.jd = twin.jd  # same text elsewhere: no second extraction
                else:
                    try:
                        jd = ctx.task.extractor.extract(row.raw_text, row.apply_url)
                    except Exception as e:  # noqa: BLE001 - one bad posting must not stop the run
                        log.warning(
                            "enrich extract failed catalog=%s error=%s",
                            row.id,
                            type(e).__name__,
                        )
                        continue
                    row.jd = jd.model_dump(mode="json")
                session.commit()
        ready = [r for r in rows if r.jd is not None]
        texts = [
            embed_text(JobDescription.model_validate(r.jd), r.title) for r in ready
        ]
        for r, vec in zip(ready, embedder.embed_documents(texts), strict=True):
            r.embedding, r.embedding_model = vec, embedder.name
            done += 1
        session.commit()
    log.info("enrich done enriched=%d", done)
    return done


# --- dedupe ----------------------------------------------------------------------
def _norm_title(t: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", t.lower()).strip()


def _loc_key(r: CatalogJob) -> str:
    return "remote" if r.remote else (r.city or r.location or "").strip().lower()


def _as_utc(dt: datetime) -> datetime:
    return dt.replace(tzinfo=UTC) if dt.tzinfo is None else dt


def dedupe(ctx: DiscoveryContext) -> int:
    """Same company + normalised title + location within 30 days: keep the employer's
    ATS record and point the others at it. Recomputed from scratch, so idempotent."""
    window = timedelta(days=settings.discovery_dedupe_window_days)
    marked = 0
    with ctx.session_factory() as session:
        groups: dict[tuple, list[CatalogJob]] = {}
        for r in RepositoryManager(session).catalog.open_jobs():
            groups.setdefault(
                (r.company_id, _norm_title(r.title), _loc_key(r)), []
            ).append(r)
        for rows in groups.values():
            rows.sort(key=lambda r: (_as_utc(r.first_seen), r.id))
            clusters: list[list[CatalogJob]] = []
            for r in rows:
                if (
                    clusters
                    and _as_utc(r.first_seen) - _as_utc(clusters[-1][0].first_seen)
                    <= window
                ):
                    clusters[-1].append(r)
                else:
                    clusters.append([r])
            for cl in clusters:
                keep = min(
                    cl,
                    key=lambda r: (r.source == HIMALAYAS, _as_utc(r.first_seen), r.id),
                )
                for r in cl:
                    want = None if r is keep else keep.id
                    if r.duplicate_of != want:
                        r.duplicate_of = want
                        marked += want is not None
        session.commit()
    log.info("dedupe newly_marked=%d", marked)
    return marked


# --- sweep closed ----------------------------------------------------------------
def sweep_closed(ctx: DiscoveryContext) -> int:
    """Postings not seen for N days are checked with is_open; closed ones get closed_at."""
    closed = 0
    with ctx.session_factory() as session:
        repos = RepositoryManager(session)
        now = ctx.now()
        stale = repos.catalog.stale_open(
            now - timedelta(days=settings.discovery_close_after_days)
        )
        sources: dict[tuple[str, str | None], JobSource] = {}
        for row in stale:
            company = repos.catalog.company(row.company_id)
            token = company.board_token if company else None
            key = (row.source, token)
            try:
                src = sources.get(key) or sources.setdefault(
                    key, build_source(row.source, ctx.http, token)
                )
                if src.is_open(row.external_id):
                    row.last_seen = now  # confirmed open; check again later
                else:
                    row.closed_at = now
                    closed += 1
            except (HttpStatus, DeniedHost, TransientError, BoardGone) as e:
                log.warning(
                    "sweep check failed catalog=%s error=%s", row.id, type(e).__name__
                )
        session.commit()
    log.info("sweep_closed closed=%d checked=%d", closed, len(stale))
    return closed


# --- ATS detection ----------------------------------------------------------------
def detect_company(ctx: DiscoveryContext, company_id: str) -> bool:
    with ctx.session_factory() as session:
        company = RepositoryManager(session).catalog.company(company_id)
        if company is None or not company.careers_url:
            return False
        found = ctx.detector.detect(company.careers_url)
        company.last_detected_at, company.redetect = ctx.now(), False
        if found:
            ats, token = found
            clash = session.scalar(
                select(Company).where(
                    Company.ats == ats,
                    Company.board_token == token,
                    Company.id != company.id,
                )
            )
            if clash is None:
                company.ats, company.board_token = ats, token
            else:
                found = None
                log.info("ats detect clash company=%s other=%s", company.id, clash.id)
        # Nothing found (or unreachable): keep any known board rather than lose it.
        try:
            session.commit()
        except IntegrityError:
            session.rollback()
            return False
        log.info("ats detected company=%s ats=%s", company_id, company.ats)
        return found is not None


def detect_stale(ctx: DiscoveryContext) -> int:
    with ctx.session_factory() as session:
        before = ctx.now() - timedelta(days=settings.discovery_redetect_days)
        ids = [
            c.id for c in RepositoryManager(session).catalog.companies_to_detect(before)
        ]
    return sum(detect_company(ctx, i) for i in ids)


# --- orchestration -----------------------------------------------------------------
def sync_all(ctx: DiscoveryContext) -> int:
    with ctx.session_factory() as session:
        ids = [c.id for c in RepositoryManager(session).catalog.companies_with_ats()]
    jobs: list[tuple[str | None, str | None]] = [(None, HIMALAYAS)] + [
        (i, None) for i in ids
    ]
    workers = ctx.workers if ctx.workers is not None else settings.discovery_workers
    if workers <= 1:
        return sum(_sync_one(ctx, c, s) for c, s in jobs)
    with ThreadPoolExecutor(max_workers=workers) as pool:
        return sum(pool.map(lambda a: _sync_one(ctx, *a), jobs))


def active_user_ids(session: Session) -> list:
    return list(
        session.scalars(
            select(User.id)
            .where(
                User.status == "active",
                User.id.in_(
                    select(Profile.user_id).where(Profile.status == "approved")
                ),
            )
            .order_by(User.id)
        )
    )


def run_daily(ctx: DiscoveryContext) -> dict[str, int]:
    """Steps 1-6. Himalayas and ATS fan-out, enrich once, dedupe, sweep, recommendations."""
    stats = {"detected": detect_stale(ctx)}
    stats["seen"] = sync_all(ctx)
    stats["enriched"] = enrich(ctx)
    stats["deduped"] = dedupe(ctx)
    stats["closed"] = sweep_closed(ctx)
    with ctx.session_factory() as session:
        users = active_user_ids(session)
    if ctx.task.queue is not None:
        for uid in users:
            ctx.task.queue.enqueue("build_recommendations", user_id=str(uid))
    stats["users_queued"] = len(users)
    log.info("run_daily %s", stats)
    return stats
