from typing import Any

from app.apply.adapters.dom import DomAdapter
from app.apply.policy import host_of


class GreenhouseAdapter(DomAdapter):
    """boards.greenhouse.io / job-boards.greenhouse.io application forms."""

    name = "greenhouse"
    form_selector = "form#application_form, form#application-form, form#greenhouse-form"
    submit_selector = "#submit_app, button[type=submit], input[type=submit]"
    confirm_text = (
        "thank you for applying",
        "your application has been submitted",
        "application submitted",
    )
    confirm_url = ("/confirmation",)

    def matches(self, url: str, page: Any) -> bool:
        host = host_of(url)
        if host.endswith("greenhouse.io"):
            return True
        try:
            return bool(page.query_selector("form#application_form, #grnhse_app"))
        except Exception:  # noqa: BLE001
            return False
