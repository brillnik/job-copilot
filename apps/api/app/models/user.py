import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import JSON, DateTime, Integer, String, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


def _now() -> datetime:
    return datetime.now(UTC)


class User(Base):
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    auth0_sub: Mapped[str] = mapped_column(String(255), unique=True)
    email: Mapped[str | None] = mapped_column(String(320))
    name: Mapped[str | None] = mapped_column(String(255))
    # active | deleting. A deleting account rejects every request.
    status: Mapped[str] = mapped_column(String(16), default="active")
    # Tokens issued at or before this instant are rejected (logout-all, deletion).
    sessions_valid_after: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True)
    )
    preferences: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    # Autopilot settings (off by default): enabled, ack_version, min_score,
    # daily_apply_cap, sites_opt_in, digest_time, last_digest_date.
    autopilot: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    preferences_rev: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_now, onupdate=_now
    )
