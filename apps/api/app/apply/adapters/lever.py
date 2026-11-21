from typing import Any
from urllib.parse import urlparse, urlunparse

from app.apply.adapters.dom import DomAdapter
from app.apply.policy import host_of


class LeverAdapter(DomAdapter):
    """jobs.lever.co postings: the form lives at <posting>/apply."""

    name = "lever"
    form_selector = "form#application-form, form.postings-form, form[action*='apply']"
    submit_selector = "#btn-submit, button.postings-btn, button[type=submit]"
    confirm_text = (
        "application submitted",
        "thanks for applying",
        "thank you for applying",
    )
    confirm_url = ("/thanks",)

    def matches(self, url: str, page: Any) -> bool:
        if host_of(url).endswith("lever.co"):
            return True
        try:
            return bool(page.query_selector("form#application-form, .postings-btn"))
        except Exception:  # noqa: BLE001
            return False

    def prepare(self, page: Any) -> None:
        p = urlparse(page.url)
        if host_of(page.url).endswith("lever.co") and not p.path.rstrip("/").endswith(
            "/apply"
        ):
            page.goto(
                urlunparse(p._replace(path=p.path.rstrip("/") + "/apply", query=""))
            )
        super().prepare(page)
