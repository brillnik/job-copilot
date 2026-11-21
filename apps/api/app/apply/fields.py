"""Plain data shared by adapters, the mapper and the pre-submit check."""

from dataclasses import dataclass, field
from pathlib import Path

# Where a form value may come from. Anything else blocks submission.
ALLOWED_SOURCES = frozenset(
    {"profile", "settings", "saved", "drafted", "user", "approved_pdf"}
)


@dataclass
class FormField:
    key: str
    selector: str
    kind: str  # text|textarea|select|checkbox|radio|file|email|tel|number|url
    label: str
    required: bool = False
    options: list[str] = field(default_factory=list)  # labels (select / radio)
    option_values: dict[str, str] = field(default_factory=dict)  # label -> value


@dataclass
class Planned:
    key: str
    label: str
    required: bool
    kind: str
    value: str | Path | None = None
    source: str | None = None
    field_type: str = "other"
    confidence: float = 1.0


@dataclass
class ReadBack:
    """What the page holds after filling: used by the pre-submit check."""

    value: str = ""
    checked: bool = False
    files: list[tuple[str, int]] = field(default_factory=list)  # (name, size)


@dataclass(frozen=True)
class ApprovedFile:
    """The approved PDF of this application's run: name and size are what the form
    must report back."""

    path: Path
    name: str
    size: int
