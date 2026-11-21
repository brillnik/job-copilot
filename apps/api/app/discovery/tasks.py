"""Task entry points for discovery. Registered in app/tasks/runtime.py; also run by
`python -m app.discovery.cli`. All are idempotent."""

import logging
import uuid
from collections.abc import Callable
from typing import Any

from app.discovery import pipeline
from app.discovery.detector import AtsDetector
from app.discovery.http import Fetcher
from app.discovery.lists_loader import sync_lists as load_lists
from app.discovery.pipeline import DiscoveryContext
from app.services.recommendation import build_recommendations as _build
from app.tasks.jobs import TaskContext

log = logging.getLogger(__name__)


def build_discovery_context(task: TaskContext) -> DiscoveryContext:
    return DiscoveryContext(task=task, http=Fetcher(), detector=AtsDetector())


def sync_source(
    ctx: DiscoveryContext, company_id: str | None = None, source: str | None = None
) -> int:
    seen = pipeline._sync_one(ctx, company_id, source)
    pipeline.enrich(ctx)
    return seen


def detect_ats(ctx: DiscoveryContext, company_id: str) -> bool:
    return pipeline.detect_company(ctx, company_id)


def sweep_closed(ctx: DiscoveryContext) -> int:
    return pipeline.sweep_closed(ctx)


def sync_lists(ctx: DiscoveryContext) -> int:
    with ctx.session_factory() as session:
        n = load_lists(session)
    return n


def build_recommendations(ctx: DiscoveryContext, user_id: uuid.UUID | str) -> int:
    n = _build(ctx.task, user_id, now=ctx.now())
    if (
        ctx.task.queue is not None
    ):  # Autopilot users: save / tailor / apply (idempotent)
        ctx.task.queue.enqueue("autopilot_tick", user_id=str(user_id))
    return n


def sync_catalog(ctx: DiscoveryContext) -> dict[str, int]:
    """The whole daily pipeline (steps 1-6)."""
    return pipeline.run_daily(ctx)


_DCTX: dict[int, DiscoveryContext] = {}


def registry_entries(task: TaskContext) -> dict[str, Callable[..., Any]]:
    def dctx() -> DiscoveryContext:
        if id(task) not in _DCTX:
            _DCTX[id(task)] = build_discovery_context(task)
        return _DCTX[id(task)]

    return {
        "sync_source": lambda **kw: sync_source(dctx(), **kw),
        "detect_ats": lambda **kw: detect_ats(dctx(), **kw),
        "sweep_closed": lambda **kw: sweep_closed(dctx(), **kw),
        "sync_lists": lambda **kw: sync_lists(dctx(), **kw),
        "build_recommendations": lambda **kw: build_recommendations(dctx(), **kw),
        "sync_catalog": lambda **kw: sync_catalog(dctx(), **kw),
    }
