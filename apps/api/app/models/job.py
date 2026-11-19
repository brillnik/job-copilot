import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import (
    JSON,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    Uuid,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base

# Job statuses
PROCESSING = "processing"
NEEDS_PASTE = "needs_paste"
NEW = "new"
TAILORING = "tailoring"
IN_REVIEW = "in_review"
APPROVED = "approved"
REJECTED = "rejected"
ARCHIVED = "archived"
FAILED = "failed"

# Run statuses; the first three are "active" (at most one per job).
RUN_ACTIVE = ("queued", "running", "awaiting_input")


def _now() -> datetime:
    return datetime.now(UTC)


def _id() -> str:
    return uuid.uuid4().hex


class Job(Base):
    __tablename__ = "jobs"
    __table_args__ = (
        Index("ix_jobs_user_status_created", "user_id", "status", "created_at"),
        Index("ix_jobs_user_url", "user_id", "url"),
        Index("ix_jobs_user_content_hash", "user_id", "content_hash"),
    )

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_id)
    user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    source: Mapped[str] = mapped_column(String(8))  # url | text | image
    url: Mapped[str | None] = mapped_column(String(2048))  # normalised
    raw_text: Mapped[str | None] = mapped_column(Text)
    image_id: Mapped[str | None] = mapped_column(String(32))
    status: Mapped[str] = mapped_column(String(16), default=PROCESSING)
    status_reason: Mapped[str | None] = mapped_column(String(512))
    company: Mapped[str | None] = mapped_column(String(255))
    title: Mapped[str | None] = mapped_column(String(255))
    score: Mapped[int | None] = mapped_column(Integer)
    score_breakdown: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    musts: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list)
    red_flags: Mapped[list[str]] = mapped_column(JSON, default=list)
    max_pages_override: Mapped[int | None] = mapped_column(Integer)
    content_hash: Mapped[str | None] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_now, onupdate=_now
    )


class JdExtraction(Base):
    __tablename__ = "jd_extractions"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_id)
    job_id: Mapped[str] = mapped_column(
        String(32), ForeignKey("jobs.id", ondelete="CASCADE"), unique=True
    )
    user_id: Mapped[uuid.UUID] = mapped_column(Uuid, index=True)
    jd: Mapped[dict[str, Any]] = mapped_column(JSON)
    extractor_version: Mapped[str] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


class AgentRun(Base):
    __tablename__ = "agent_runs"
    __table_args__ = (
        # At most one active run per job, enforced by the database.
        Index(
            "uq_agent_runs_active_job",
            "job_id",
            unique=True,
            sqlite_where=text("status IN ('queued','running','awaiting_input')"),
            postgresql_where=text("status IN ('queued','running','awaiting_input')"),
        ),
    )

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_id)
    user_id: Mapped[uuid.UUID] = mapped_column(Uuid, index=True)
    job_id: Mapped[str] = mapped_column(
        String(32), ForeignKey("jobs.id", ondelete="CASCADE"), index=True
    )
    profile_version: Mapped[int] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(16), default="queued")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


class RunQuota(Base):
    """Runs started per user per local day; incremented with a conditional UPDATE."""

    __tablename__ = "run_quota"

    user_id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True)
    day: Mapped[str] = mapped_column(String(10), primary_key=True)
    used: Mapped[int] = mapped_column(Integer, default=0)


class UserAnswer(Base):
    """Remembered answers to "do you have this skill?" prompts."""

    __tablename__ = "user_answers"
    __table_args__ = (UniqueConstraint("user_id", "skill"),)

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_id)
    user_id: Mapped[uuid.UUID] = mapped_column(Uuid, index=True)
    skill: Mapped[str] = mapped_column(String(255))
    answer: Mapped[str] = mapped_column(String(8))  # yes | no
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


class Event(Base):
    """Per-user event stream, read by polling GET /events?after=<id>."""

    __tablename__ = "events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[uuid.UUID] = mapped_column(Uuid, index=True)
    type: Mapped[str] = mapped_column(String(32))
    payload: Mapped[dict[str, Any]] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


class ImageUpload(Base):
    __tablename__ = "image_uploads"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_id)
    user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    storage_key: Mapped[str] = mapped_column(String(512), unique=True)
    media_type: Mapped[str] = mapped_column(String(32))
    size: Mapped[int] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
