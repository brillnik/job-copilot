import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import JSON, Boolean, DateTime, Index, Integer, String, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


def _now() -> datetime:
    return datetime.now(UTC)


class TrainingConsentLog(Base):
    """Append-only: a row per change; the current state is the row with the highest id."""

    __tablename__ = "training_consent_log"
    __table_args__ = (Index("ix_training_consent_user_id_id", "user_id", "id"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[uuid.UUID] = mapped_column(Uuid)
    enabled: Mapped[bool] = mapped_column(Boolean)
    policy_version: Mapped[str] = mapped_column(String(32))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


class ExtractorShadowRun(Base):
    """One local-vs-Claude comparison. Booleans and counts only: no text, no values,
    and deliberately no user_id (a shared system table)."""

    __tablename__ = "extractor_shadow_runs"
    __table_args__ = (Index("ix_shadow_kind_slice", "kind", "slice"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    kind: Mapped[str] = mapped_column(String(8))  # profile | jd
    slice: Mapped[str] = mapped_column(String(64))
    results: Mapped[dict[str, Any]] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
