from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

Column = Literal["approved", "applied", "response", "interview", "offer", "rejected"]


class Card(BaseModel):
    id: str
    job_id: str
    company: str | None
    title: str | None
    score: int | None
    column: Column
    applied_at: datetime | None
    notes_preview: str | None
    updated_at: datetime
    rev: int  # send back as If-Match on PATCH


class CardDetail(Card):
    notes: str | None
    position: float
    history: list[dict]


class Stats(BaseModel):
    applied_this_week: int
    response_rate: (
        float | None
    )  # responses / applied, last 30 days; null if none applied
    avg_match_score: float | None
    counts: dict[Column, int]


class Board(BaseModel):
    columns: dict[Column, list[Card]]
    stats: Stats


class TrackerPatch(BaseModel):
    model_config = ConfigDict(extra="forbid")

    column: Column | None = None
    position: int | None = Field(
        default=None, ge=0, description="0-based index within the target column"
    )
    applied_at: datetime | None = None
    notes: str | None = Field(default=None, max_length=10_000)

    @model_validator(mode="after")
    def something_to_change(self) -> "TrackerPatch":
        if not self.model_fields_set:
            raise ValueError("send at least one field to change")
        if "column" in self.model_fields_set and self.column is None:
            raise ValueError("column must not be null")
        if "position" in self.model_fields_set and self.position is None:
            raise ValueError("position must not be null")
        return self


class TrackerAdd(BaseModel):
    model_config = ConfigDict(extra="forbid")

    job_id: str = Field(max_length=32)
    column: Column = "applied"
