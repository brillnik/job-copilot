import uuid
from datetime import UTC, datetime

from sqlalchemy import DateTime, Index, String, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


def _now() -> datetime:
    return datetime.now(UTC)


def _id() -> str:
    return uuid.uuid4().hex


class ConsentLog(Base):
    """Append-only: a new row per consent; rows are never updated."""

    __tablename__ = "consent_log"
    __table_args__ = (Index("ix_consent_user_created", "user_id", "created_at"),)

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_id)
    user_id: Mapped[uuid.UUID] = mapped_column(Uuid)
    policy_version: Mapped[str] = mapped_column(String(32))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


class Export(Base):
    __tablename__ = "exports"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_id)
    user_id: Mapped[uuid.UUID] = mapped_column(Uuid, index=True)
    status: Mapped[str] = mapped_column(String(16), default="queued")
    # queued | running | ready | failed | expired
    storage_key: Mapped[str | None] = mapped_column(String(512))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    ready_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class DeletionAudit(Base):
    """Proof that an account was erased. Keyed hashes only: no personal data."""

    __tablename__ = "deletion_audit"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_id)
    user_id_hash: Mapped[str] = mapped_column(String(64), unique=True)
    # Keyed hash of the identity-provider subject; lets us refuse a stale token
    # from before the deletion without keeping the subject itself.
    sub_hash: Mapped[str] = mapped_column(String(64), index=True)
    deleted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
