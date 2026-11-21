from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class PairCodeOut(BaseModel):
    code: str
    expires_at: datetime


class PairIn(BaseModel):
    code: str = Field(min_length=4, max_length=32)
    device_name: str | None = Field(default=None, max_length=120)


class PairOut(BaseModel):
    token_id: str
    token: str  # shown once; only its hash is stored


class TokenOut(BaseModel):
    id: str
    device_name: str | None
    created_at: datetime
    last_used_at: datetime | None
    revoked_at: datetime | None


class ClipIn(BaseModel):
    url: str = Field(max_length=2048)
    title: str | None = Field(default=None, max_length=300)
    company: str | None = Field(default=None, max_length=300)
    text: str = Field(min_length=1, max_length=100_000)


class ApplyResultIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: Literal["submitted", "skipped", "error"]
    reason: str | None = Field(default=None, max_length=64)
    screenshot: str | None = Field(
        default=None, max_length=6_000_000
    )  # base64 PNG/JPEG
