from typing import Any, Literal

from pydantic import BaseModel, Field


class RecommendationOut(BaseModel):
    id: str
    catalog_job_id: str
    score: int
    reasons: list[str]
    digest_date: str
    action: Literal["none", "saved", "dismissed"]
    job_id: str | None = None  # the v1 job, once saved
    title: str
    company: str | None
    location: str | None
    remote: bool
    apply_url: str  # all applies use this link
    # Required by the source's terms: show it wherever the posting is shown.
    source_attribution: dict[str, Any] | None = None


class RecommendationList(BaseModel):
    items: list[RecommendationOut]


class DismissIn(BaseModel):
    reason: str | None = Field(default=None, max_length=200)


class RefreshOut(BaseModel):
    # ready: today's digest already exists; building: a digest is being built from the
    # catalogue; syncing: the catalogue is empty so discovery is running first.
    status: Literal["ready", "building", "syncing"]
