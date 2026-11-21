from datetime import datetime

from pydantic import BaseModel, Field


class TrainingConsentIn(BaseModel):
    enabled: bool
    policy_version: str = Field(min_length=1, max_length=32)


class TrainingConsentOut(BaseModel):
    enabled: bool
    policy_version: str | None = None
    at: datetime | None = None
