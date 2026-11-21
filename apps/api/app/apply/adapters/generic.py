from typing import Any

from app.apply.adapters.dom import DomAdapter


class GenericAdapter(DomAdapter):
    """Unknown forms. Matches any page with exactly one form; every unmapped required
    field goes through the FormFallback and, failing high confidence, skips."""

    name = "generic"
    uses_fallback = True
    confirm_text = (
        "thank you for applying",
        "application submitted",
        "application received",
        "thanks for applying",
    )

    def matches(self, url: str, page: Any) -> bool:
        try:
            return len(page.query_selector_all("form")) == 1
        except Exception:  # noqa: BLE001
            return False
