import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


def _hex_id() -> str:
    return uuid.uuid4().hex


class Bullet(BaseModel):
    # Stable id; generation cites it as source_id, so keep it across edits.
    id: str = Field(default_factory=_hex_id, max_length=32)
    text: str = Field(min_length=1, max_length=1000)


class Contact(BaseModel):
    name: str | None = None
    email: str | None = None
    phone: str | None = None
    location: str | None = None
    links: list[str] = []


class Experience(BaseModel):
    id: str = Field(default_factory=_hex_id, max_length=32)
    company: str
    title: str | None = None
    location: str | None = None
    start: str | None = None
    end: str | None = None
    bullets: list[Bullet] = []


class Project(BaseModel):
    id: str = Field(default_factory=_hex_id, max_length=32)
    name: str
    description: str | None = None
    bullets: list[Bullet] = []


class Education(BaseModel):
    id: str = Field(default_factory=_hex_id, max_length=32)
    institution: str
    degree: str | None = None
    start: str | None = None
    end: str | None = None


class ProfileData(BaseModel):
    contact: Contact = Contact()
    summary: str | None = None
    experience: list[Experience] = []
    projects: list[Project] = []
    education: list[Education] = []
    skills: list[str] = []


class ProfileOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    status: Literal["draft", "approved"]
    version: int | None
    resume_id: str | None
    data: ProfileData
    created_at: datetime
    updated_at: datetime
    approved_at: datetime | None


class BulletSearch(BaseModel):
    """Retrieval request: one query per JD must-have."""

    queries: list[str] = Field(min_length=1, max_length=30)
    per_query: int = Field(default=5, ge=1, le=20)
    limit: int = Field(default=15, ge=1, le=50)
    max_per_entry: int = Field(default=3, ge=1, le=10)


class RankedBullet(BaseModel):
    source_id: str
    text: str
    section: str
    entry_id: str
    entry_label: str
    score: float
    matched_queries: list[str]


class BulletSearchOut(BaseModel):
    profile_version: int
    bullets: list[RankedBullet]
