from app.apply.adapters.ashby import AshbyAdapter
from app.apply.adapters.base import FormAdapter
from app.apply.adapters.generic import GenericAdapter
from app.apply.adapters.greenhouse import GreenhouseAdapter
from app.apply.adapters.lever import LeverAdapter


def default_adapters() -> list[FormAdapter]:
    """Specific ATS adapters first; the generic fallback adapter is always last."""
    return [GreenhouseAdapter(), LeverAdapter(), AshbyAdapter(), GenericAdapter()]


def ats_for_url(url: str) -> str:
    """Best guess from the URL alone (the page decides at run time)."""
    from app.apply.policy import host_of

    host = host_of(url)
    for name, suffix in (
        ("greenhouse", "greenhouse.io"),
        ("lever", "lever.co"),
        ("ashby", "ashbyhq.com"),
    ):
        if host.endswith(suffix):
            return name
    return "unknown"


__all__ = ["FormAdapter", "ats_for_url", "default_adapters"]
