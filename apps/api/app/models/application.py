"""Job applications (one per user and job) and the counters that cap them."""

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
    Uuid,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base

STATUSES = (
    "queued",
    "running",
    "waiting_for_user",
    "submitted",
    "skipped",
    "failed",
    "cancelled",
)
ACTIVE = ("queued", "running", "waiting_for_user")


def _now() -> datetime:
    return datetime.now(UTC)


def _id() -> str:
    return uuid.uuid4().hex


class Application(Base):
    __tablename__ = "applications"
    __table_args__ = (
        Index("uq_applications_user_job", "user_id", "job_id", unique=True),
        Index("ix_applications_user_status", "user_id", "status"),
    )

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_id)
    user_id: Mapped[uuid.UUID] = mapped_column(Uuid)
    job_id: Mapped[str] = mapped_column(
        String(32), ForeignKey("jobs.id", ondelete="CASCADE")
    )
    run_id: Mapped[str] = mapped_column(String(32))
    channel: Mapped[str] = mapped_column(String(12))  # playwright | extension
    mode: Mapped[str] = mapped_column(
        String(10), default="manual"
    )  # manual | autopilot
    ats: Mapped[str | None] = mapped_column(String(16))
    site: Mapped[str] = mapped_column(String(32))  # cap / pause key
    status: Mapped[str] = mapped_column(String(16), default="queued")
    skip_reason: Mapped[str | None] = mapped_column(String(64))
    apply_url: Mapped[str] = mapped_column(String(2048))  # the direct link
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    answers_used: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list)
    screenshot_keys: Mapped[list[str]] = mapped_column(JSON, default=list)
    # Manual mode: required fields with no value, waiting for POST /answer.
    pending_fields: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list)
    # Explicit user answers {normalised label: value}, used on the next attempt.
    provided_answers: Mapped[dict[str, str]] = mapped_column(JSON, default=dict)
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    slot_held: Mapped[bool] = mapped_column(Boolean, default=False)
    slot_day: Mapped[str | None] = mapped_column(String(10))
    slot_hour: Mapped[str | None] = mapped_column(String(13))
    error: Mapped[str | None] = mapped_column(Text)  # reason code only
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_now, onupdate=_now
    )


class ApplyQuota(Base):
    """Applications per user per site per local day; site '*' is the user's total.

    Incremented with a conditional UPDATE (`used < cap`), like RunQuota.
    """

    __tablename__ = "apply_quota"

    user_id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True)
    day: Mapped[str] = mapped_column(String(10), primary_key=True)
    site: Mapped[str] = mapped_column(String(32), primary_key=True)
    used: Mapped[int] = mapped_column(Integer, default=0)


class AtsHourlyQuota(Base):
    """Applications per ATS per UTC hour, across all users (no user data)."""

    __tablename__ = "ats_hourly_quota"

    ats: Mapped[str] = mapped_column(String(16), primary_key=True)
    hour: Mapped[str] = mapped_column(String(13), primary_key=True)  # YYYY-MM-DDTHH
    used: Mapped[int] = mapped_column(Integer, default=0)


class SiteState(Base):
    """Consecutive blocks per user and site; two in a row pause the site."""

    __tablename__ = "apply_site_state"

    user_id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True)
    site: Mapped[str] = mapped_column(String(32), primary_key=True)
    consecutive_blocks: Mapped[int] = mapped_column(Integer, default=0)
    paused_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_reason: Mapped[str | None] = mapped_column(String(64))
