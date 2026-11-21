"""FormAdapter: the interface every ATS (and the unknown-form fallback) implements.

    matches(url, page) -> bool        does this adapter recognise the page?
    read_fields(page) -> [FormField]  the visible form controls
    fill(page, values)                values: field key -> text, or a Path for a file
    submit(page)                      click the form's submit control (once)

plus prepare() (reach the form, e.g. Lever's /apply), read_back() (for the pre-submit
check) and confirmed() (is there a confirmation?). Adapters never decide WHAT to fill.
"""

from collections.abc import Callable
from pathlib import Path
from typing import Any, Protocol

from app.apply.fields import FormField, ReadBack


class FormAdapter(Protocol):
    name: str
    uses_fallback: bool

    def matches(self, url: str, page: Any) -> bool: ...

    def prepare(self, page: Any) -> None: ...

    def read_fields(self, page: Any) -> list[FormField]: ...

    def fill(
        self,
        page: Any,
        values: dict[str, str | Path],
        fields: list[FormField],
        pace: Callable[[], None],
    ) -> None: ...

    def read_back(self, page: Any, fields: list[FormField]) -> dict[str, ReadBack]: ...

    def submit(self, page: Any) -> None: ...

    def confirmed(self, page: Any) -> bool: ...
