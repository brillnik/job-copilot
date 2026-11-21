import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import (
    JSON,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    Uuid,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base

COLUMNS = ("approved", "applied", "response", "interview", "offer", "rejected")


def _now() -> datetime:
    return datetime.now(UTC)


class TrackerCard(Base):
    __tablename__ = "tracker_cards"
    __table_args__ = (
        Index("ix_tracker_user_column_position", "user_id", "column", "position"),
        Index("uq_tracker_user_job", "user_id", "job_id", unique=True),
    )

    id: Mapped[str] = mapped_column(
        String(32), primary_key=True, default=lambda: uuid.uuid4().hex
    )
    user_id: Mapped[uuid.UUID] = mapped_column(Uuid)
    job_id: Mapped[str] = mapped_column(
        String(32), ForeignKey("jobs.id", ondelete="CASCADE")
    )
    column: Mapped[str] = mapped_column(String(16))
    position: Mapped[float] = mapped_column(Float)
    applied_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    notes: Mapped[str | None] = mapped_column(Text)
    history: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list)
    rev: Mapped[int] = mapped_column(Integer, default=1)  # ETag for If-Match
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_now, onupdate=_now
    )
