import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import JSON, DateTime, Index, String, Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


def _now() -> datetime:
    return datetime.now(UTC)


def _id() -> str:
    return uuid.uuid4().hex


class ScreeningAnswer(Base):
    """A saved answer to an application-form question, reusable by meaning."""

    __tablename__ = "screening_answers"
    __table_args__ = (Index("ix_screening_user_type", "user_id", "field_type"),)

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_id)
    user_id: Mapped[uuid.UUID] = mapped_column(Uuid, index=True)
    question: Mapped[str] = mapped_column(Text)
    normalised_question: Mapped[str] = mapped_column(Text)
    answer: Mapped[str] = mapped_column(Text)
    field_type: Mapped[str] = mapped_column(String(32))
    embedding: Mapped[list[Any]] = mapped_column(JSON, default=list)
    embedding_model: Mapped[str | None] = mapped_column(String(128))
    source: Mapped[str] = mapped_column(String(16))  # user | approved_apply
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_now, onupdate=_now
    )
