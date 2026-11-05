import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import JSON, DateTime, ForeignKey, Integer, String, Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base

DRAFT = "draft"
APPROVED = "approved"


def _now() -> datetime:
    return datetime.now(UTC)


def _id() -> str:
    return uuid.uuid4().hex


class Profile(Base):
    """A user's profile. At most one draft per user; approved rows are immutable versions."""

    __tablename__ = "profiles"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_id)
    user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    status: Mapped[str] = mapped_column(String(16), index=True)
    version: Mapped[int | None] = mapped_column(Integer)
    data: Mapped[dict[str, Any]] = mapped_column(JSON)
    resume_id: Mapped[str | None] = mapped_column(
        String(32), ForeignKey("resumes.id", ondelete="SET NULL")
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_now, onupdate=_now
    )
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class ProfileBullet(Base):
    """One retrievable bullet of an approved profile, indexed once per version."""

    __tablename__ = "profile_bullets"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_id)
    profile_id: Mapped[str] = mapped_column(
        String(32), ForeignKey("profiles.id", ondelete="CASCADE"), index=True
    )
    user_id: Mapped[uuid.UUID] = mapped_column(Uuid, index=True)
    source_id: Mapped[str] = mapped_column(String(32))
    section: Mapped[str] = mapped_column(String(16))
    entry_id: Mapped[str] = mapped_column(String(32))
    entry_label: Mapped[str] = mapped_column(String(512))
    text: Mapped[str] = mapped_column(Text)
    embedding: Mapped[list[float]] = mapped_column(JSON)
