import uuid
from datetime import datetime
from typing import Any, Literal, Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

WorkMode = Literal["onsite", "hybrid", "remote", "unknown"]
MustStatus = Literal["have", "ask", "missing", "unknown"]
JobStatus = Literal[
    "processing",
    "needs_paste",
    "new",
    "tailoring",
    "in_review",
    "approved",
    "rejected",
    "archived",
    "failed",
]


class JobDescription(BaseModel):
    """Structured posting. Missing info is null / []; strings are verbatim from the source."""

    title: str | None = None
    company: str | None = None
    location: str | None = None
    work_mode: WorkMode = "unknown"
    experience_years_min: float | None = None
    experience_years_max: float | None = None
    ctc_lpa_min: float | None = None  # lakhs per annum
    ctc_lpa_max: float | None = None
    seniority: str | None = None
    must_have: list[str] = []
    nice_to_have: list[str] = []
    responsibilities: list[str] = []
    keywords: list[str] = []
    red_flags: list[str] = []
    requested_resume_pages: int | None = Field(default=None, ge=1, le=3)
    source_url: str | None = None


class Must(BaseModel):
    skill: str
    status: MustStatus
    evidence_bullet_id: str | None = None


class JobAdd(BaseModel):
    source: Literal["url", "text", "image"]
    url: str | None = Field(default=None, max_length=2048)
    text: str | None = Field(default=None, max_length=100_000)
    image_id: str | None = Field(default=None, max_length=32)

    @model_validator(mode="after")
    def exactly_one_matching_input(self) -> Self:
        given = {
            k for k in ("url", "text", "image_id") if getattr(self, k) not in (None, "")
        }
        want = {"url": "url", "text": "text", "image": "image_id"}[self.source]
        if given != {want}:
            raise ValueError(f"source '{self.source}' requires only '{want}'")
        return self


class JobAddOut(BaseModel):
    job_id: str
    status: JobStatus | None = None
    duplicate: bool = False


class JobPatch(BaseModel):
    """Exactly one of the fields may be sent."""

    model_config = ConfigDict(extra="forbid")

    text: str | None = Field(default=None, max_length=100_000)
    archived: bool | None = None
    max_pages_override: Literal[1, 2, 3] | None = None

    @model_validator(mode="after")
    def exactly_one(self) -> Self:
        if len(self.model_fields_set) != 1:
            raise ValueError("send exactly one of text, archived, max_pages_override")
        if "text" in self.model_fields_set and not (self.text or "").strip():
            raise ValueError("text must not be empty")
        if "archived" in self.model_fields_set and self.archived is None:
            raise ValueError("archived must be true or false")
        return self


class TailorIn(BaseModel):
    confirm_red_flags: bool = False


class TailorOut(BaseModel):
    run_id: str


class JobOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    source: str
    url: str | None
    status: JobStatus
    status_reason: str | None
    company: str | None
    title: str | None
    score: int | None
    red_flags: list[str]
    max_pages_override: int | None
    created_at: datetime
    updated_at: datetime


class JobSummary(BaseModel):
    id: str
    company: str | None
    title: str | None
    location: str | None
    ctc_lpa_min: float | None
    ctc_lpa_max: float | None
    score: int | None
    musts_summary: str | None  # "4 of 6"
    status: JobStatus
    red_flags: list[str]
    created_at: datetime


class JobList(BaseModel):
    items: list[JobSummary]
    next_cursor: str | None


class RunRef(BaseModel):
    id: str
    status: str


class JobDetail(BaseModel):
    job: JobOut
    jd: JobDescription | None
    score_breakdown: dict[str, Any] | None
    musts: list[Must]
    latest_run: RunRef | None


class ImageOut(BaseModel):
    image_id: str


class EventOut(BaseModel):
    id: int
    type: str
    payload: dict[str, Any]
    created_at: datetime


class EventList(BaseModel):
    events: list[EventOut]
    last_id: int


class JobIdOnly(BaseModel):
    id: uuid.UUID
