from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

Site = Literal["wellfound", "naukri", "hiring_cafe"]


class SiteOptIn(BaseModel):
    acknowledged: bool
    acknowledged_at: datetime | None = None
    policy_version: str | None = None
    paused: bool = False


class AutopilotOut(BaseModel):
    enabled: bool
    min_score: int
    daily_apply_cap: int
    digest_time: str
    sites_opt_in: dict[str, SiteOptIn]
    policy_version: str  # the text version a client must acknowledge
    acknowledged_version: str | None
    paused_sites: list[str] = []


class SiteOptInPut(BaseModel):
    model_config = ConfigDict(extra="forbid")

    opt_in: bool
    # Required when opting in: must equal the current policy text version.
    acknowledgement_version: str | None = None


class AutopilotPut(BaseModel):
    model_config = ConfigDict(extra="forbid")

    enabled: bool | None = None
    # Required when enabling: must equal the current policy text version.
    acknowledgement_version: str | None = None
    min_score: int | None = Field(default=None, ge=0, le=100)
    daily_apply_cap: int | None = Field(default=None, ge=1)
    digest_time: str | None = Field(default=None, pattern=r"^([01]\d|2[0-3]):[0-5]\d$")
    sites: dict[Site, SiteOptInPut] | None = None
    resume_sites: list[str] | None = None  # clear an automatic site pause


class DigestItem(BaseModel):
    application_id: str
    job_id: str
    company: str | None
    title: str | None
    status: str
    reason: str | None = None
    direct_link: str | None = None


class DigestOut(BaseModel):
    date: str
    submitted: list[DigestItem]
    skipped: list[DigestItem]
    needs_a_person: list[DigestItem]
