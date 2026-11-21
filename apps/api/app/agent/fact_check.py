"""Deterministic fact check of a tailored resume against an approved profile.

This is code, never an LLM: the agent's output and every user edit pass through it,
so nothing the profile (or the user's own confirmed answers) does not support can
reach a PDF. Logs must carry codes and counts only, never the text.
"""

import re
from collections.abc import Sequence
from dataclasses import dataclass, field

from app.agent.lexicon import TECH_TERMS
from app.schemas.profile import ProfileData
from app.schemas.run import TailoredBullet, TailoredResume, Violation

# Digits glued to a letter are part of a name (K8s, S3, EC2), not a figure.
_NUMBER = re.compile(r"(?<![A-Za-z])\d[\d,]*(?:\.\d+)?%?")


def _numbers(text: str) -> set[str]:
    return {m.group().replace(",", "").rstrip(".") for m in _NUMBER.finditer(text)}


def _has_term(text: str, term: str) -> bool:
    return (
        re.search(rf"(?<![\w+#.]){re.escape(term)}(?![\w+#])", text, re.IGNORECASE)
        is not None
    )


@dataclass
class Facts:
    """What may be claimed: profile text per bullet, whole-profile text, confirmed skills."""

    bullets: dict[str, str]
    corpus: str
    skills: set[str]
    confirmed: set[str] = field(default_factory=set)
    confirmed_text: str = ""
    lexicon: frozenset[str] = TECH_TERMS
    groups: dict[str, set[str]] = field(default_factory=dict)  # term -> its aliases

    def forms(self, term: str) -> set[str]:
        return {term, *self.groups.get(term, ())}

    def supported_in(self, term: str, text: str) -> bool:
        if term in self.confirmed:
            return True
        return any(
            _has_term(text, f) or _has_term(self.confirmed_text, f)
            for f in self.forms(term)
        )


def build_facts(
    profile: ProfileData,
    answers: Sequence[tuple[str, str, str | None]] = (),  # (skill, yes|no, detail)
    extra_terms: Sequence[str] = (),
    synonyms: dict[str, list[str]] | None = None,
) -> Facts:
    bullets = {b.id: b.text for e in profile.experience for b in e.bullets}
    bullets |= {b.id: b.text for p in profile.projects for b in p.bullets}
    parts = [profile.summary or "", *profile.skills, *bullets.values()]
    parts += [f"{e.title or ''} {e.company}" for e in profile.experience]
    parts += [f"{p.name} {p.description or ''}" for p in profile.projects]
    yes = [(s.lower(), d or "") for s, a, d in answers if a == "yes"]

    groups: dict[str, set[str]] = {}
    for canon, aliases in (synonyms or {}).items():
        family = {canon.lower(), *(a.lower() for a in aliases)}
        for name in family:
            groups[name] = family - {name}
    lexicon = frozenset(TECH_TERMS | set(groups) | {t.lower() for t in extra_terms})
    return Facts(
        bullets=bullets,
        corpus="\n".join(parts),
        skills={s.lower() for s in profile.skills},
        confirmed={s for s, _ in yes},
        confirmed_text="\n".join(f"{s} {d}" for s, d in yes),
        lexicon=lexicon,
        groups=groups,
    )


def _unsupported_terms(facts: Facts, text: str, allowed: str) -> list[str]:
    return sorted(
        t
        for t in facts.lexicon
        if _has_term(text, t) and not facts.supported_in(t, allowed)
    )


def check_bullet(facts: Facts, bullet: TailoredBullet) -> list[Violation]:
    source = facts.bullets.get(bullet.source_id)
    if source is None:
        return [
            Violation(
                code="unknown_source",
                field="bullet",
                source_id=bullet.source_id,
                message="This bullet does not come from your profile",
            )
        ]
    found = []
    for n in sorted(_numbers(bullet.text) - _numbers(source)):
        found.append(
            Violation(
                code="invented_number",
                field="bullet",
                source_id=bullet.source_id,
                term=n,
                message=f"The number {n} is not in your profile bullet",
            )
        )
    for t in _unsupported_terms(facts, bullet.text, source):
        found.append(
            Violation(
                code="unsupported_skill",
                field="bullet",
                source_id=bullet.source_id,
                term=t,
                message=f"{t} is not supported by this bullet or your confirmed skills",
            )
        )
    return found


def check_prose(facts: Facts, field_name: str, text: str | None) -> list[Violation]:
    """Summary and cover note may draw on the whole profile, but invent nothing."""
    if not text:
        return []
    found = [
        Violation(
            code="invented_number",
            field=field_name,
            term=n,
            message=f"The number {n} is not in your profile",
        )
        for n in sorted(_numbers(text) - _numbers(facts.corpus + facts.confirmed_text))
    ]
    found += [
        Violation(
            code="unsupported_skill",
            field=field_name,
            term=t,
            message=f"{t} is not supported by your profile or confirmed skills",
        )
        for t in _unsupported_terms(facts, text, facts.corpus)
    ]
    return found


def check_skills(facts: Facts, skills: list[str]) -> list[Violation]:
    out = []
    for s in skills:
        key = s.lower()
        if key in facts.skills or key in facts.confirmed:
            continue
        if any(f in facts.skills or f in facts.confirmed for f in facts.forms(key)):
            continue
        out.append(
            Violation(
                code="unsupported_skill",
                field="skills_order",
                term=s,
                message=f"{s} is not in your profile or confirmed skills",
            )
        )
    return out


def fact_check(facts: Facts, resume: TailoredResume) -> list[Violation]:
    found: list[Violation] = []
    for b in resume.bullets:
        found += check_bullet(facts, b)
    found += check_prose(facts, "summary", resume.summary)
    found += check_prose(facts, "cover_note", resume.cover_note)
    found += check_skills(facts, resume.skills_order)
    return found
