import uuid
from datetime import UTC, datetime

from sqlalchemy import (
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Index,
    String,
    Text,
    Uuid,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base

CLASSES = (
    "interview",
    "rejection",
    "recruiter_reply",
    "assessment",
    "offer",
    "other",
)
PENDING, ACCEPTED, DISMISSED = "pending", "accepted", "dismissed"


def _now() -> datetime:
    return datetime.now(UTC)


def _id() -> str:
    return uuid.uuid4().hex


class GmailConnection(Base):
    """One per user. The refresh token is Fernet-encrypted; the address is only ever
    stored as a keyed hash (used to map Pub/Sub pushes back to a user)."""

    __tablename__ = "gmail_connections"
    __table_args__ = (Index("ix_gmail_connections_email_hash", "email_hash"),)

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_id)
    user_id: Mapped[uuid.UUID] = mapped_column(Uuid, unique=True)
    token_ciphertext: Mapped[str] = mapped_column(Text)
    email_hash: Mapped[str] = mapped_column(String(64))
    history_id: Mapped[str | None] = mapped_column(String(32))
    status: Mapped[str] = mapped_column(String(16), default="active")  # | reauth
    connected_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_now
    )
    last_synced_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class EmailEvent(Base):
    """What we concluded about one message. Never holds the subject, sender or body."""

    __tablename__ = "email_events"
    __table_args__ = (
        Index("uq_email_user_message", "user_id", "gmail_message_id", unique=True),
        Index("ix_email_user_suggestion", "user_id", "suggestion_status"),
    )

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_id)
    user_id: Mapped[uuid.UUID] = mapped_column(Uuid)
    gmail_message_id: Mapped[str] = mapped_column(String(64))
    job_id: Mapped[str | None] = mapped_column(
        String(32), ForeignKey("jobs.id", ondelete="SET NULL")
    )
    classification: Mapped[str] = mapped_column(String(16))
    confidence: Mapped[float] = mapped_column(Float)
    applied_to_tracker: Mapped[bool] = mapped_column(Boolean, default=False)
    suggested_column: Mapped[str | None] = mapped_column(String(16))
    suggestion_status: Mapped[str | None] = mapped_column(String(16))
    received_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
