from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

FieldType = Literal[
    "notice_period",
    "current_ctc",
    "expected_ctc",
    "relocation",
    "work_authorization",
    "years_experience",
    "link",
    "open",
    "other",
]


class ScreeningField(BaseModel):
    """One question on an application form."""

    label: str = Field(min_length=1, max_length=1000)
    field_type: FieldType = "other"
    tool: str | None = Field(default=None, max_length=100)  # years_experience
    link_kind: str | None = Field(
        default=None, max_length=50
    )  # link: linkedin, github...


class ScreeningValue(BaseModel):
    value: str
    source: Literal["settings", "profile", "saved", "drafted"]


class ScreeningAnswerOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    question: str
    answer: str
    field_type: str
    source: str
    updated_at: datetime


class ScreeningAnswerList(BaseModel):
    items: list[ScreeningAnswerOut]


class ScreeningAnswerPut(BaseModel):
    answer: str = Field(min_length=1, max_length=4000)
    question: str | None = Field(default=None, min_length=1, max_length=1000)
