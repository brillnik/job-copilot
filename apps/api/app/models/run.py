import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    Uuid,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


def _now() -> datetime:
    return datetime.now(UTC)


def _id() -> str:
    return uuid.uuid4().hex


class RunEvent(Base):
    """Append-only log of one run (status changes, steps). `seq` is the SSE event id."""

    __tablename__ = "run_events"
    __table_args__ = (UniqueConstraint("run_id", "seq"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    run_id: Mapped[str] = mapped_column(
        String(32), ForeignKey("agent_runs.id", ondelete="CASCADE"), index=True
    )
    user_id: Mapped[uuid.UUID] = mapped_column(Uuid, index=True)
    seq: Mapped[int] = mapped_column(Integer)
    type: Mapped[str] = mapped_column(String(32))
    payload: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    ts: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


class Draft(Base):
    """One tailored resume per agent iteration; user edits update the latest in place."""

    __tablename__ = "drafts"
    __table_args__ = (UniqueConstraint("run_id", "iteration"),)

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_id)
    run_id: Mapped[str] = mapped_column(
        String(32), ForeignKey("agent_runs.id", ondelete="CASCADE"), index=True
    )
    user_id: Mapped[uuid.UUID] = mapped_column(Uuid, index=True)
    iteration: Mapped[int] = mapped_column(Integer)
    tailored: Mapped[dict[str, Any]] = mapped_column(JSON)  # TailoredResume
    violations: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list)
    coverage: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    pages: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    outcome: Mapped[str | None] = mapped_column(Text)  # what this iteration concluded
    pdf_key: Mapped[str | None] = mapped_column(String(512))
    edited: Mapped[bool] = mapped_column(Boolean, default=False)
    rev: Mapped[int] = mapped_column(Integer, default=1)  # ETag for If-Match
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_now, onupdate=_now
    )


class Approval(Base):
    """The user's decision on a run; at most one per run."""

    __tablename__ = "approvals"
    __table_args__ = (
        Index("ix_approvals_user_created", "user_id", "created_at"),
        UniqueConstraint("run_id"),
    )

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_id)
    user_id: Mapped[uuid.UUID] = mapped_column(Uuid)
    run_id: Mapped[str] = mapped_column(
        String(32), ForeignKey("agent_runs.id", ondelete="CASCADE")
    )
    job_id: Mapped[str] = mapped_column(String(32))
    decision: Mapped[str] = mapped_column(String(8))  # approved | rejected
    reasons: Mapped[list[str]] = mapped_column(JSON, default=list)
    edits_applied: Mapped[bool] = mapped_column(Boolean, default=False)
    final: Mapped[dict[str, Any] | None] = mapped_column(JSON)  # TailoredResume
    pdf_key: Mapped[str | None] = mapped_column(String(512))
    file_name: Mapped[str | None] = mapped_column(String(255))
    # Embedding of the JD (title + must-haves) this resume was approved for; used to
    # find similar past approvals as style examples. Null if embedding was unavailable.
    jd_embedding: Mapped[list[float] | None] = mapped_column(JSON)
    jd_embedding_model: Mapped[str | None] = mapped_column(String(128))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
