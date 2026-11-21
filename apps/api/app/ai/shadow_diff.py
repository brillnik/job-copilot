"""Per-field comparison of the local extractor against Claude.

Output holds booleans and counts only: never a value. Each field carries tp/fp/fn
over normalised items (Claude's output is the reference), so the report can compute
F1 without ever seeing text.
"""

from typing import Any

from pydantic import BaseModel

from app.ai.local import Outcome
from app.ai.text import norm
from app.schemas.job import JobDescription
from app.schemas.profile import ProfileData


def _items(value: Any) -> set[str]:
    if value is None:
        return set()
    if isinstance(value, (list, tuple, set)):
        return {i for v in value for i in _items(v)}
    if isinstance(value, float):
        return {repr(round(value, 2))}
    return {n} if (n := norm(str(value))) else set()


def profile_fields(p: ProfileData) -> dict[str, set[str]]:
    c = p.contact
    return {
        "contact.name": _items(c.name),
        "contact.email": _items(c.email),
        "contact.phone": _items(c.phone),
        "contact.location": _items(c.location),
        "contact.links": _items(c.links),
        "summary": _items(p.summary),
        "experience": {
            norm(f"{e.company}|{e.title}|{e.start}|{e.end}") for e in p.experience
        },
        "experience.bullets": _items([b.text for e in p.experience for b in e.bullets]),
        "projects": _items([x.name for x in p.projects]),
        "education": {norm(f"{e.institution}|{e.degree}") for e in p.education},
        "skills": _items(p.skills),
    }


def jd_fields(j: JobDescription) -> dict[str, set[str]]:
    return {
        name: _items(getattr(j, name))
        for name in (
            "title", "company", "location", "work_mode", "experience_years_min",
            "experience_years_max", "ctc_lpa_min", "ctc_lpa_max", "seniority",
            "must_have", "nice_to_have", "responsibilities", "keywords", "red_flags",
            "requested_resume_pages",
        )
    }  # fmt: skip


def field_sets(result: BaseModel) -> dict[str, set[str]]:
    if isinstance(result, ProfileData):
        return profile_fields(result)
    return jd_fields(result)  # type: ignore[arg-type]


def diff_results(
    reference: BaseModel, local: Outcome | None, *, local_error: bool = False
) -> dict[str, Any]:
    """The record stored per shadow run. No values, ever."""
    if local_error or local is None:
        return {"local_error": True, "schema_valid": False, "fields": {}}
    if not local.schema_valid or local.checked is None:
        return {
            "local_error": False,
            "schema_valid": False,
            "emitted": 0,
            "hallucinated": 0,
            "fields": {},
        }
    ref, got = field_sets(reference), field_sets(local.checked)
    fields = {}
    for name, want in ref.items():
        have = got[name]
        tp = len(want & have)
        fields[name] = {
            "match": want == have,
            "tp": tp,
            "fp": len(have - want),
            "fn": len(want - have),
        }
    return {
        "local_error": False,
        "schema_valid": True,
        "emitted": local.emitted,
        "hallucinated": local.hallucinated,
        "fields": fields,
    }


def log_line(results: dict[str, Any]) -> str:
    """Field names and match flags only, safe for logs."""
    if not results.get("schema_valid"):
        return "schema_valid=0"
    flags = " ".join(f"{k}={int(v['match'])}" for k, v in results["fields"].items())
    return f"schema_valid=1 hallucinated={results['hallucinated']} {flags}"
