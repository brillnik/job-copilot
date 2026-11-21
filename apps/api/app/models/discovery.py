"""Discovery catalogue (shared, no user_id) and per-user recommendations / device tokens.

Companies and CatalogJob are written only by discovery workers; API routes read them.
"""

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


class Company(Base):
    __tablename__ = "companies"
    __table_args__ = (UniqueConstraint("ats", "board_token"),)

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_id)
    name: Mapped[str] = mapped_column(String(255))
    name_key: Mapped[str] = mapped_column(String(255), unique=True)  # normalised name
    careers_url: Mapped[str | None] = mapped_column(String(2048))
    ats: Mapped[str] = mapped_column(String(16), default="unknown")
    board_token: Mapped[str | None] = mapped_column(String(255))
    lists: Mapped[list[str]] = mapped_column(JSON, default=list)  # yc | india_ai
    last_detected_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    redetect: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


class CatalogJob(Base):
    __tablename__ = "catalog_jobs"
    __table_args__ = (
        UniqueConstraint("source", "external_id"),
        Index("ix_catalog_jobs_closed_last_seen", "closed_at", "last_seen"),
    )

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_id)
    source: Mapped[str] = mapped_column(String(16))  # himalayas|greenhouse|lever|ashby
    external_id: Mapped[str] = mapped_column(String(255))
    company_id: Mapped[str] = mapped_column(
        String(32), ForeignKey("companies.id", ondelete="CASCADE"), index=True
    )
    title: Mapped[str] = mapped_column(String(512))
    location: Mapped[str | None] = mapped_column(String(512))
    city: Mapped[str | None] = mapped_column(String(128))
    remote: Mapped[bool] = mapped_column(Boolean, default=False)
    country_restrictions: Mapped[list[str]] = mapped_column(JSON, default=list)
    apply_url: Mapped[str] = mapped_column(String(2048))  # every apply uses this
    source_attribution: Mapped[dict[str, Any] | None] = mapped_column(
        JSON(none_as_null=True)
    )
    raw_text: Mapped[str] = mapped_column(Text)
    content_hash: Mapped[str] = mapped_column(String(64))
    jd: Mapped[dict[str, Any] | None] = mapped_column(
        JSON(none_as_null=True)
    )  # JobDescription
    embedding: Mapped[list[float] | None] = mapped_column(JSON(none_as_null=True))
    embedding_model: Mapped[str | None] = mapped_column(String(64))
    duplicate_of: Mapped[str | None] = mapped_column(String(32))  # kept ATS record
    first_seen: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    last_seen: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class Recommendation(Base):
    __tablename__ = "recommendations"
    __table_args__ = (
        Index("ix_recommendations_user_digest", "user_id", "digest_date"),
        UniqueConstraint("user_id", "catalog_job_id", "digest_date"),
    )

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_id)
    user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    catalog_job_id: Mapped[str] = mapped_column(
        String(32), ForeignKey("catalog_jobs.id", ondelete="CASCADE"), index=True
    )
    score: Mapped[int] = mapped_column(Integer)
    reasons: Mapped[list[str]] = mapped_column(JSON, default=list)
    digest_date: Mapped[str] = mapped_column(String(10))
    action: Mapped[str] = mapped_column(
        String(16), default="none"
    )  # none|saved|dismissed
    dismiss_reason: Mapped[str | None] = mapped_column(String(200))
    job_id: Mapped[str | None] = mapped_column(String(32))  # v1 job once saved
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


class ExtensionToken(Base):
    """A paired browser-extension device. Only a keyed hash of the token is stored."""

    __tablename__ = "extension_tokens"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_id)
    user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    token_hash: Mapped[str] = mapped_column(String(64), unique=True)
    device_name: Mapped[str | None] = mapped_column(String(120))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    last_used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class ExtensionPairingCode(Base):
    """One-time pairing code (hash only), valid for 10 minutes."""

    __tablename__ = "extension_pairing_codes"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_id)
    user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    code_hash: Mapped[str] = mapped_column(String(64), unique=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
