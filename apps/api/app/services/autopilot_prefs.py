"""Autopilot settings stored on users.autopilot, over the defaults. Off by default."""

from typing import Any

from app.core.config import settings
from app.models.user import User

SITES = ("wellfound", "naukri", "hiring_cafe")


def autopilot_of(user: User | None) -> dict[str, Any]:
    stored = (user.autopilot if user else None) or {}
    out: dict[str, Any] = {
        "enabled": False,
        "ack_version": None,
        "min_score": settings.autopilot_default_min_score,
        "daily_apply_cap": settings.autopilot_default_daily_cap,
        "sites_opt_in": {},
        "digest_time": settings.autopilot_default_digest_time,
        "last_digest_date": None,
    }
    out.update({k: v for k, v in stored.items() if k in out})
    return out


def autopilot_enabled(user: User | None) -> bool:
    """On only with an acknowledgement of the CURRENT policy text version."""
    a = autopilot_of(user)
    return bool(a["enabled"] and a["ack_version"] == settings.autopilot_policy_version)


def daily_cap(user: User | None) -> int:
    return max(
        1, min(autopilot_of(user)["daily_apply_cap"], settings.autopilot_daily_cap_max)
    )


def site_opted_in(user: User | None, site: str) -> bool:
    """Explicit acknowledged_at plus the current policy version, or nothing is queued."""
    e = autopilot_of(user)["sites_opt_in"].get(site)
    return bool(
        e
        and e.get("acknowledged_at")
        and e.get("policy_version") == settings.autopilot_policy_version
    )


def site_cap(site: str) -> int:
    return settings.autopilot_site_caps.get(site, settings.autopilot_default_site_cap)
