"""Past approved resumes as STYLE examples, and the per-user A/B switch.

Retrieval is always filtered by user_id. Only ids are ever logged.
"""

import hashlib
import logging
import math
import uuid
from collections.abc import Callable
from contextlib import AbstractContextManager
from typing import Protocol

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.agent.llm import Example
from app.ai.embeddings import Embedder
from app.core.config import settings
from app.models.run import Approval
from app.schemas.job import JobDescription

log = logging.getLogger(__name__)


def jd_text(jd: JobDescription) -> str:
    """What identifies a JD for similarity: its title and must-haves."""
    return " ".join([jd.title or "", *jd.must_have]).strip()


def cosine(a: list[float], b: list[float]) -> float:
    if not a or not b or len(a) != len(b):
        return 0.0
    dot = sum(x * y for x, y in zip(a, b, strict=True))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(y * y for y in b))
    return dot / (na * nb) if na and nb else 0.0


def embed_jd(embedder: Embedder, jd: JobDescription) -> list[float] | None:
    text = jd_text(jd)
    if not text:
        return None
    return embedder.embed_documents([text])[0]


def bucket(user_id: uuid.UUID | str) -> int:
    """Stable 0-99 bucket for a user (hash of the id), for A/B assignment."""
    key = uuid.UUID(str(user_id)).hex
    return int.from_bytes(hashlib.sha256(key.encode()).digest()[:4]) % 100


def examples_enabled_for(user_id: uuid.UUID | str | None) -> bool:
    """Feature flag AND the user's deterministic A/B arm."""
    if not settings.tailor_examples_enabled or user_id is None:
        return False
    return bucket(user_id) < settings.tailor_examples_ab_pct


class ExampleSource(Protocol):
    def retrieve(self, user_id: str, jd: JobDescription) -> list[Example]: ...


class DbExampleSource:
    def __init__(
        self,
        session_factory: Callable[[], AbstractContextManager[Session]],
        embedder: Embedder,
    ) -> None:
        self.session_factory = session_factory
        self.embedder = embedder

    def retrieve(self, user_id: str, jd: JobDescription) -> list[Example]:
        uid = uuid.UUID(str(user_id))
        query = embed_jd(self.embedder, jd)
        if query is None:
            return []
        with self.session_factory() as session:
            rows = session.scalars(
                select(Approval).where(
                    Approval.user_id == uid,
                    Approval.decision == "approved",
                    Approval.jd_embedding.is_not(None),
                )
            ).all()
            scored = []
            for a in rows:
                if a.jd_embedding_model != self.embedder.name:
                    continue  # a different vector space is not comparable
                sim = cosine(query, a.jd_embedding or [])
                if sim >= settings.tailor_examples_min_sim:
                    scored.append((sim, a))
            scored.sort(key=lambda t: t[0], reverse=True)
            out = []
            for sim, a in scored[: settings.tailor_examples_max]:
                final = a.final or {}
                out.append(
                    Example(
                        approval_id=a.id,
                        title=None,
                        summary=final.get("summary"),
                        bullets=[b.get("text", "") for b in final.get("bullets", [])],
                        similarity=round(sim, 4),
                    )
                )
        log.info(
            "tailor examples user=%s approvals=%s", uid, [e.approval_id for e in out]
        )
        return out
