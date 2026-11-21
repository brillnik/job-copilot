"""Decide a value (and its source) for every form field. Never invents anything.

Order for each field: an explicit user answer, then the contact details in the approved
profile, then `ScreeningService.answer_for` (settings, profile, saved-answer bank, or a
fact-checked draft for open questions). No source -> value None (and, if the field is
required, the application stops).
"""

import re
import uuid
from pathlib import Path
from typing import Any

from app.apply.fields import ApprovedFile, FormField, Planned
from app.schemas.job import JobDescription
from app.schemas.profile import ProfileData
from app.schemas.screening import ScreeningField
from app.services.screening import ScreeningService, normalise

DEMOGRAPHIC = re.compile(
    r"gender|race|ethnic|veteran|disabilit|sexual orientation|pronoun|hispanic|lgbt",
    re.IGNORECASE,
)
RESUME = re.compile(r"\b(resume|cv|curriculum)\b", re.IGNORECASE)
YEARS = re.compile(
    r"years?.*\b(?:with|using|in)\s+(?P<tool>[A-Za-z0-9+#.\-]+(?: [A-Za-z0-9+#.\-]+){0,2})\s*[?.:]?\s*$",
    re.IGNORECASE,
)


def split_name(full: str | None) -> tuple[str | None, str | None]:
    parts = (full or "").split()
    if not parts:
        return None, None
    return parts[0], (" ".join(parts[1:]) or None)


def classify(f: FormField) -> ScreeningField:
    """A ScreeningField for answer_for, from the label text only."""
    label = f.label
    low = label.lower()
    t = "other"
    tool = kind = None
    if re.search(r"notice period|serving notice|joining time", low):
        t = "notice_period"
    elif re.search(r"current (ctc|salary|compensation)|present (ctc|salary)", low):
        t = "current_ctc"
    elif re.search(
        r"expected (ctc|salary|compensation)|salary expectation|desired (ctc|salary)",
        low,
    ):
        t = "expected_ctc"
    elif "relocat" in low:
        t = "relocation"
    elif re.search(r"authori[sz]ed to work|work authori|sponsorship|visa", low):
        t = "work_authorization"
    elif m := YEARS.search(label):
        t, tool = "years_experience", m.group("tool").strip()
    else:
        for k in ("linkedin", "github", "portfolio", "twitter", "website"):
            if k in low:
                t, kind = "link", k
                break
        else:
            if f.kind == "textarea" or len(label) > 60:
                t = "open"
    return ScreeningField(label=label[:1000], field_type=t, tool=tool, link_kind=kind)  # type: ignore[arg-type]


def fit_option(value: str, f: FormField) -> str | None:
    """The option label matching `value`, or None (no guess)."""
    if not f.options:
        return value
    want = value.strip().lower()
    for o in f.options:
        if o.strip().lower() == want:
            return o
    if want in ("yes", "y", "true"):
        for o in f.options:
            if o.strip().lower().startswith("yes"):
                return o
    if want in ("no", "n", "false"):
        for o in f.options:
            if o.strip().lower().startswith("no"):
                return o
    return None


class Mapper:
    def __init__(
        self,
        user_id: uuid.UUID,
        screening: ScreeningService,
        profile: ProfileData,
        account_email: str | None,
        jd: JobDescription | None,
        provided: dict[str, str],
        approved: ApprovedFile,
    ) -> None:
        self.user_id, self.screening, self.profile = user_id, screening, profile
        self.email = profile.contact.email or account_email
        self.email_src = "profile" if profile.contact.email else "settings"
        self.jd, self.provided, self.approved = jd, provided, approved

    def plan(self, fields: list[FormField]) -> list[Planned]:
        return [self._one(f) for f in fields]

    # -- one field --------------------------------------------------------------
    def _one(self, f: FormField) -> Planned:
        p = Planned(f.key, f.label, f.required, f.kind)
        if f.kind == "file":
            if RESUME.search(f.label) or RESUME.search(f.key):
                p.value, p.source = self.approved.path, "approved_pdf"
            return p
        given = self.provided.get(normalise(f.label))
        if given:
            return self._set(p, f, given, "user")
        if DEMOGRAPHIC.search(f.label):
            return p  # never guessed; blocks only if the form requires it
        got = self._contact(f) or self._screened(p, f)
        if got is not None:
            return self._set(p, f, got[0], got[1])
        return p

    def _set(self, p: Planned, f: FormField, value: str, source: str) -> Planned:
        fitted = fit_option(value, f) if f.kind in ("select", "radio") else value
        if fitted is None or not str(fitted).strip():
            return p  # an answer that is not one of the options is not mapped
        p.value, p.source = fitted, source
        return p

    def _contact(self, f: FormField) -> tuple[str, str] | None:
        label, key, c = f.label.lower(), f.key.lower(), self.profile.contact
        first, last = split_name(c.name)
        hay = f"{label} {key}"
        if f.kind in ("checkbox", "radio", "select"):
            return None
        if re.search(r"first[ _-]?name|given name", hay):
            return (first, "profile") if first else None
        if re.search(r"last[ _-]?name|surname|family name", hay):
            return (last, "profile") if last else None
        if f.kind == "email" or re.search(r"e-?mail", hay):
            return (self.email, self.email_src) if self.email else None
        if f.kind == "tel" or re.search(r"phone|mobile|contact number", hay):
            return (c.phone, "profile") if c.phone else None
        if re.search(r"^(full )?name\b|full name|your name|_systemfield_name", hay):
            return (c.name, "profile") if c.name else None
        if re.search(r"current location|^location|\bcity\b", label):
            return (c.location, "profile") if c.location else None
        return None

    def _screened(self, p: Planned, f: FormField) -> tuple[str, str] | None:
        sf = classify(f)
        p.field_type = sf.field_type
        got = self.screening.answer_for(self.user_id, sf, self.jd)
        return (got["value"], got["source"]) if got else None


def approved_pdf_file(tmp_dir: Path, name: str, data: bytes) -> ApprovedFile:
    path = tmp_dir / name
    path.write_bytes(data)
    return ApprovedFile(path=path, name=name, size=len(data))


def intended_report(plan: list[Planned]) -> list[dict[str, Any]]:
    """Every field the application intends to touch (stored as answers_used)."""
    return [
        {
            "key": p.key,
            "label": p.label[:200],
            "required": p.required,
            "source": p.source,
            "value": "[approved resume pdf]" if p.source == "approved_pdf" else p.value,
        }
        for p in plan
        if p.value is not None
    ]
