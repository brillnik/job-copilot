"""Wires real components into the task context; used by the in-process queue."""

from collections.abc import Callable
from functools import lru_cache, partial
from typing import Any

from app.ai.embeddings import Embedder, FastEmbedEmbedder, HashingEmbedder
from app.ai.factory import build_jd_extractor, build_transcriber
from app.ai.fetcher import HttpJobFetcher
from app.core.config import settings
from app.db.session import SessionLocal
from app.storage.base import Storage
from app.tasks import jobs
from app.tasks.queue import InProcessQueue, TaskQueue


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
    )


def registry() -> dict[str, Callable[..., Any]]:
    ctx = get_context()
    return {
        "extract_jd": partial(jobs.extract_jd, ctx),
        "rescore_jobs": partial(jobs.rescore_jobs, ctx),
        "tailor": partial(jobs.tailor, ctx),
    }


@lru_cache
def get_queue() -> TaskQueue:
    return InProcessQueue(registry)
