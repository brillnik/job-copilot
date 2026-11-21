from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

ApplicationStatus = Literal[
    "queued",
    "running",
    "waiting_for_user",
    "submitted",
    "skipped",
    "failed",
    "cancelled",
]


class PendingField(BaseModel):
    key: str
    label: str
    kind: str = "text"
    field_type: str = "other"
    options: list[str] = []


class ApplicationOut(BaseModel):
    id: str
    job_id: str
    run_id: str
    company: str | None = None
    title: str | None = None
    channel: Literal["playwright", "extension"]
    mode: Literal["manual", "autopilot"]
    ats: str | None
    site: str
    status: ApplicationStatus
    skip_reason: str | None
    direct_link: str  # where the person can apply themselves
    submitted_at: datetime | None
    answers_used: list[dict[str, Any]] = []
    screenshots: list[str] = []  # signed URLs, valid for 5 minutes
    pending_fields: list[PendingField] = []
    attempts: int
    created_at: datetime
    updated_at: datetime


class ApplicationList(BaseModel):
    items: list[ApplicationOut]
    next_cursor: str | None = None


class FieldAnswer(BaseModel):
    model_config = ConfigDict(extra="forbid")

    key: str = Field(min_length=1, max_length=255)
    value: str = Field(min_length=1, max_length=4000)
    remember: bool = True  # save to the screening-answer bank for next time


class ApplicationAnswerIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    answers: list[FieldAnswer] = Field(min_length=1, max_length=50)
