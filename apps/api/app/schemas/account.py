import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.core.config import settings


class Preferences(BaseModel):
    """users.preferences. Strict: every field required, unknown fields rejected."""

    model_config = ConfigDict(extra="forbid")

    target_roles: list[str] = Field(min_length=1, max_length=10)
    cities: list[str] = Field(max_length=30)
    current_ctc_lpa: float = Field(ge=0, le=500)
    expected_ctc_lpa: float = Field(ge=0, le=500)
    notice_days: int = Field(ge=0, le=180)
    default_length: Literal[1, 2, 3, "auto"]
    template: Literal["classic", "compact"]
    daily_cap: int = Field(ge=1)
    coverage_target: float
    theme: Literal["light", "dark", "system"]

    @field_validator("target_roles")
    @classmethod
    def _roles(cls, roles: list[str]) -> list[str]:
        cleaned = [r.strip() for r in roles]
        if any(not r or len(r) > 80 for r in cleaned):
            raise ValueError("each role must be 1-80 characters")
        return list(dict.fromkeys(cleaned))

    @field_validator("cities")
    @classmethod
    def _cities(cls, cities: list[str]) -> list[str]:
        known = {c.lower(): c for c in settings.allowed_cities}
        bad = [c for c in cities if c.strip().lower() not in known]
        if bad:
            raise ValueError(
                "unknown city; allowed: " + ", ".join(settings.allowed_cities)
            )
        return list(dict.fromkeys(known[c.strip().lower()] for c in cities))

    @field_validator("coverage_target")
    @classmethod
    def _coverage(cls, value: float) -> float:
        if value not in (0.5, 0.6, 0.7, 0.8):
            raise ValueError("coverage_target must be one of 0.5, 0.6, 0.7, 0.8")
        return value

    @field_validator("daily_cap")
    @classmethod
    def _cap(cls, cap: int) -> int:
        if cap > settings.daily_cap_max:
            raise ValueError(f"daily_cap must be at most {settings.daily_cap_max}")
        return cap


class PreferencesOut(BaseModel):
    """What GET returns: stored values, or defaults for a user who never saved any."""

    target_roles: list[str]
    cities: list[str]
    current_ctc_lpa: float
    expected_ctc_lpa: float
    notice_days: int
    default_length: Literal[1, 2, 3, "auto"]
    template: Literal["classic", "compact"]
    daily_cap: int
    coverage_target: float
    theme: Literal["light", "dark", "system"]


class SettingsOut(BaseModel):
    preferences: PreferencesOut
    configured: bool  # false until the user saves once; preferences are defaults
    rev: int  # send back as If-Match on PUT /settings
    runs_used_today: int
    daily_cap: int
    cap_resets_at: datetime


class Consent(BaseModel):
    policy_version: str
    at: datetime


class ConsentIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    policy_version: str = Field(min_length=1, max_length=32)


class MeOut(BaseModel):
    id: uuid.UUID
    email: str | None
    name: str | None
    auth_providers: list[str]
    consent: Consent | None
    created_at: datetime
    plan: Literal["free"] = "free"


class ExportRef(BaseModel):
    export_id: str


class ExportOut(BaseModel):
    export_id: str
    status: Literal["queued", "running", "ready", "failed", "expired"]
    created_at: datetime
    expires_at: datetime | None
    download_url: str | None  # signed, valid 24 h; only when status == ready


class DeleteIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    confirm: Literal["DELETE"]


class DeleteOut(BaseModel):
    status: Literal["deleting"] = "deleting"
