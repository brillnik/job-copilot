"""Wires real components into the task context; used by the in-process queue."""

from collections.abc import Callable
from functools import lru_cache, partial
from typing import Any

from app.ai.embeddings import Embedder, FastEmbedEmbedder, HashingEmbedder
from app.ai.factory import build_jd_extractor, build_transcriber
from app.ai.fetcher import HttpJobFetcher
from app.core.config import settings
from app.db.session import SessionLocal
from app.discovery import tasks as discovery_tasks
from app.services import autopilot
from app.services.mail import LogMailer
from app.storage.base import Storage
from app.tasks import account, jobs, runs
from app.tasks import gmail as gmail_tasks
from app.tasks.queue import InProcessQueue, TaskQueue
from app.training.export import export_training_dataset


def build_storage() -> Storage:
    from app.storage.local import LocalStorage
    from app.storage.s3 import S3Storage

    if settings.storage_backend == "s3":
        return S3Storage(
            bucket=settings.s3_bucket,
            endpoint_url=settings.s3_endpoint_url or None,
            access_key=settings.s3_access_key or None,
            secret_key=settings.s3_secret_key or None,
            region=settings.s3_region,
        )
    return LocalStorage(settings.upload_dir)


def build_embedder() -> Embedder:
    if settings.embedding_backend == "hashing":
        return HashingEmbedder()
    return FastEmbedEmbedder(settings.embedding_model)


def build_agent():
    if settings.tailor_agent == "none":
        return None
    from app.agent.factory import build_tailor_agent

    return build_tailor_agent(SessionLocal, build_embedder())


@lru_cache
def get_context() -> jobs.TaskContext:
    return jobs.TaskContext(
        session_factory=SessionLocal,
        storage=build_storage(),
        extractor=build_jd_extractor(),
        transcriber=build_transcriber(),
        fetcher=HttpJobFetcher(
            settings.fetch_timeout_s,
            settings.fetch_max_bytes,
            settings.fetch_max_redirects,
        ),
        embedder=build_embedder(),
        scoring=jobs.scoring_config(),
        # TAILOR_AGENT=none (default) leaves runs queued; "graph" wires the LangGraph agent.
        agent=build_agent(),
        mailer=LogMailer(),
        queue=get_queue(),
    )


@lru_cache
def get_gmail_context() -> gmail_tasks.GmailContext:
    from app.ai.email_classifier import build_email_classifier
    from app.services.google import HttpGoogleClient

    return gmail_tasks.GmailContext(
        session_factory=SessionLocal,
        google=HttpGoogleClient(
            settings.google_client_id,
            settings.google_client_secret,
            settings.gmail_redirect_uri,
            settings.gmail_snippet_chars,
        ),
        classifier=build_email_classifier(),
        queue=get_queue(),
    )


@lru_cache
def get_apply_context():
    """Apply worker context (the `apply` registry entries; the real browser is only
    started when an application runs)."""
    from app.apply.worker import build_apply_context

    ctx = build_apply_context()
    ctx.queue = get_queue()
    return ctx


def _run_apply(**kw):
    from app.apply.runner import run_application

    return run_application(get_apply_context(), **kw)


def registry() -> dict[str, Callable[..., Any]]:
    ctx = get_context()
    return {
        "extract_jd": partial(jobs.extract_jd, ctx),
        "rescore_jobs": partial(jobs.rescore_jobs, ctx),
        "tailor": partial(runs.tailor, ctx),
        "render_pdf": partial(runs.render_pdf, ctx),
        "export_user": partial(account.export_user, ctx),
        "expire_exports": partial(account.expire_exports, ctx),
        "delete_user": partial(account.delete_user, ctx),
        "resume_deletions": partial(account.resume_deletions, ctx),
        # Gmail: poll_all_gmail should run every 15 minutes (scheduler TODO).
        "poll_gmail": lambda **kw: gmail_tasks.poll_gmail(get_gmail_context(), **kw),
        "poll_all_gmail": lambda: gmail_tasks.poll_all_gmail(get_gmail_context()),
        "export_training_dataset": partial(export_training_dataset, ctx),
        # Apply queue (entrypoint: app/apply/worker.py). With APPLY_WORKER_MODE=external
        # the separate worker polls the database instead of using this entry.
        "apply_application": lambda **kw: _run_apply(**kw),
        # Autopilot: tick after build_recommendations and from `python -m app.apply.cli`.
        "autopilot_tick": lambda **kw: autopilot.autopilot_tick(ctx, **kw),
        "autopilot_advance": lambda **kw: autopilot.autopilot_advance(ctx, **kw),
        "send_digests": lambda **kw: autopilot.send_digests(ctx, **kw),
        # Discovery (sync_catalog is also run by `python -m app.discovery.cli run-daily`).
        **discovery_tasks.registry_entries(ctx),
    }


@lru_cache
def get_queue() -> TaskQueue:
    return InProcessQueue(registry)
