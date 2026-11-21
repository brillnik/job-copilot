from typing import Any
from urllib.parse import urlparse, urlunparse

from app.apply.adapters.dom import DomAdapter
from app.apply.policy import host_of


class AshbyAdapter(DomAdapter):
    """jobs.ashbyhq.com: client-rendered form at <posting>/application."""

    name = "ashby"
    form_selector = "form, [class*='ashby-application-form']"
    submit_selector = "button[type=submit], button:has-text('Submit Application')"
    confirm_text = (
        "your application was successfully submitted",
        "application submitted",
        "thank you for applying",
    )

    def matches(self, url: str, page: Any) -> bool:
        if host_of(url).endswith("ashbyhq.com"):
            return True
        try:
            return bool(
                page.query_selector(
                    "[name='_systemfield_name'], [class*='ashby-application-form']"
                )
            )
        except Exception:  # noqa: BLE001
            return False

    def prepare(self, page: Any) -> None:
        p = urlparse(page.url)
        if host_of(page.url).endswith("ashbyhq.com") and not p.path.rstrip(
            "/"
        ).endswith("/application"):
            page.goto(
                urlunparse(
                    p._replace(path=p.path.rstrip("/") + "/application", query="")
                )
            )
        super().prepare(page)
