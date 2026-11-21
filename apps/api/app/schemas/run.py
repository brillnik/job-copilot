import uuid
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

RunStatus = Literal[
    "queued",
    "running",
    "waiting_for_user",
    "in_review",
    "approved",
    "rejected",
    "needs_attention",
    "cancelled",
]
RejectReason = Literal["wrong_emphasis", "too_generic", "factual_issue", "tone"]


class TailoredBullet(BaseModel):
    source_id: str = Field(max_length=32)  # id of the approved-profile bullet
    text: str = Field(min_length=1, max_length=1000)
    reverted: bool = False  # the agent fell back to the source text
    revert_reason: str | None = None


class TailoredResume(BaseModel):
    summary: str | None = Field(default=None, max_length=2000)
    bullets: list[TailoredBullet] = []
    skills_order: list[str] = []
    cover_note: str | None = Field(default=None, max_length=4000)


class Violation(BaseModel):
    code: str  # unknown_source | invented_number | unsupported_skill | ...
    field: str  # summary | cover_note | skills_order | bullet
    source_id: str | None = None
    term: str | None = None
    message: str
    blocked: bool = False  # an edit that was refused, not a flaw left in the draft


class Coverage(BaseModel):
    covered: list[str] = []
    missing: list[str] = []
    pct: float = 0.0


class Pages(BaseModel):
    count: int = 1
    last_page_fill: float = 0.0


# --- reading ------------------------------------------------------------------
class RunSummary(BaseModel):
    id: str
    job_id: str
    company: str | None
    title: str | None
    status: RunStatus
    flagged: bool
    score: int | None
    coverage: str | None  # "5/6"
    pages: int | None
    created_at: datetime
    top_changes: list[str] = Field(default_factory=list, max_length=3)


class RunList(BaseModel):
    items: list[RunSummary]
    next_cursor: str | None


class DiffSegment(BaseModel):
    op: Literal["same", "add", "del"]
    text: str


class BulletReview(BaseModel):
    source_id: str
    source_text: str | None
    tailored_text: str
    diff: list[DiffSegment]
    reverted: bool
    revert_reason: str | None


class IterationOut(BaseModel):
    iteration: int
    outcome: str | None


class PendingQuestion(BaseModel):
    skill: str
    prompt: str | None = None


class RunDetail(BaseModel):
    id: str
    job_id: str
    company: str | None
    title: str | None
    status: RunStatus
    status_reason: str | None
    flagged: bool
    current_step: str | None
    iteration: int
    profile_version: int
    max_pages: int | None
    pending_questions: list[PendingQuestion]
    created_at: datetime
    updated_at: datetime
    draft_rev: int | None  # send back as If-Match on PUT /runs/{id}/draft
    edited: bool
    summary: str | None
    skills_order: list[str]
    cover_note: str | None
    bullets: list[BulletReview]
    violations: list[Violation]
    coverage: Coverage | None
    pages: Pages | None
    iterations: list[IterationOut]
    has_pdf: bool


# --- writing ------------------------------------------------------------------
class Answer(BaseModel):
    model_config = ConfigDict(extra="forbid")

    skill: str = Field(min_length=1, max_length=255)
    answer: Literal["yes", "no"]
    detail: str | None = Field(default=None, max_length=1000)


class AnswerIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    answers: list[Answer] = Field(min_length=1, max_length=30)


class RunRef(BaseModel):
    run_id: str
    status: RunStatus


class BulletEdit(BaseModel):
    model_config = ConfigDict(extra="forbid")

    source_id: str = Field(max_length=32)
    text: str = Field(min_length=1, max_length=1000)


class DraftEdit(BaseModel):
    model_config = ConfigDict(extra="forbid")

    summary: str | None = Field(default=None, max_length=2000)
    bullets: list[BulletEdit] | None = None
    cover_note: str | None = Field(default=None, max_length=4000)
    skills_order: list[str] | None = Field(default=None, max_length=60)

    @model_validator(mode="after")
    def something_to_change(self) -> "DraftEdit":
        if not self.model_fields_set:
            raise ValueError("send at least one field to change")
        return self


class DraftEditOut(BaseModel):
    run: RunDetail
    applied: list[str]  # fields that passed the fact check and were saved
    violations: list[Violation]  # refused edits (blocked=true) and remaining flaws


class ApproveOut(BaseModel):
    approval_id: str
    file_name: str


class RejectIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    reasons: list[RejectReason] = Field(default_factory=list, max_length=4)
    note: str | None = Field(default=None, max_length=2000)


class RegenerateIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    max_pages: Literal[1, 2, 3] | None = None
    guidance_from_rejection: bool = True
    confirm_red_flags: bool = False


class RunEventOut(BaseModel):
    seq: int
    type: str
    payload: dict[str, Any]
    ts: datetime


class RunIdOnly(BaseModel):
    id: uuid.UUID
