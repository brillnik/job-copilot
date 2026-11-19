"""Match score: pure functions, no I/O. Evidence lookup is injected.

total = round(100 * (w_must*must_coverage + w_experience*experience_fit
                     + w_location*location_fit + w_ctc*ctc_fit + w_nice*nice_coverage))
"""

import math
import re
from collections.abc import Callable
from dataclasses import dataclass, field

from app.schemas.job import JobDescription, Must

# (skill) -> (bullet id, similarity) of the best-matching approved bullet, or None
EvidenceFinder = Callable[[str], "tuple[str, float] | None"]


@dataclass(frozen=True)
class ScoringConfig:
    w_must: float = 0.60
    w_experience: float = 0.15
    w_location: float = 0.10
    w_ctc: float = 0.10
    w_nice: float = 0.05
    evidence_min_score: float = 0.45
    ask_credit: float = 0.5
    neutral_fit: float = 0.5
    overqualified_fit: float = 0.8
    adjacency: dict[str, list[str]] = field(default_factory=dict)
    synonyms: dict[str, list[str]] = field(default_factory=dict)


@dataclass(frozen=True)
class ProfileFacts:
    """What scoring needs from the APPROVED profile."""

    skills: list[str]
    bullets: list[tuple[str, str]]  # (bullet id, text)
    years_experience: float | None
    location: str | None


@dataclass(frozen=True)
class Prefs:
    """Optional user preferences; unknown values give a neutral fit."""

    expected_ctc_lpa: float | None = None
    cities: tuple[str, ...] = ()
    open_to_remote: bool = True


@dataclass(frozen=True)
class ScoreResult:
    score: int | None
    breakdown: dict
    musts: list[Must]


def _canon(skill: str, synonyms: dict[str, list[str]]) -> str:
    s = re.sub(r"\s+", " ", skill.strip().lower())
    for canonical, aliases in synonyms.items():
        if s == canonical or s in aliases:
            return canonical
    return s


def _terms(skill: str, synonyms: dict[str, list[str]]) -> set[str]:
    c = _canon(skill, synonyms)
    return {c, *synonyms.get(c, [])}


def _mentions(text: str, terms: set[str]) -> bool:
    low = text.lower()
    return any(re.search(rf"(?<![\w+#.]){re.escape(t)}(?![\w+#])", low) for t in terms)


def classify(
    skill: str,
    profile: ProfileFacts,
    answers: dict[str, str],
    find_evidence: EvidenceFinder,
    cfg: ScoringConfig,
) -> Must:
    """have | ask | missing for one skill."""
    canon = _canon(skill, cfg.synonyms)
    terms = _terms(skill, cfg.synonyms)
    answer = answers.get(canon) or answers.get(skill.strip().lower())

    if answer == "no":  # an explicit "no" always wins
        return Must(skill=skill, status="missing")
    if answer == "yes":
        return Must(skill=skill, status="have")

    profile_skills = {_canon(s, cfg.synonyms) for s in profile.skills}
    if profile_skills & {_canon(t, cfg.synonyms) for t in terms}:
        evidence = next(
            (bid for bid, text in profile.bullets if _mentions(text, terms)), None
        )
        return Must(skill=skill, status="have", evidence_bullet_id=evidence)
    for bid, text in profile.bullets:
        if _mentions(text, terms):
            return Must(skill=skill, status="have", evidence_bullet_id=bid)

    hit = find_evidence(skill)
    if hit is not None and hit[1] >= cfg.evidence_min_score:
        return Must(skill=skill, status="have", evidence_bullet_id=hit[0])

    adjacent = {_canon(a, cfg.synonyms) for a in cfg.adjacency.get(canon, [])}
    if adjacent & profile_skills or any(
        _mentions(text, adjacent) for _, text in profile.bullets
    ):
        return Must(skill=skill, status="ask")
    return Must(skill=skill, status="missing")


def experience_fit(
    jd: JobDescription, years: float | None, cfg: ScoringConfig
) -> float:
    lo, hi = jd.experience_years_min, jd.experience_years_max
    if years is None or (lo is None and hi is None):
        return cfg.neutral_fit
    if lo is not None and years < lo:
        return max(0.0, years / lo) if lo > 0 else 1.0
    if hi is not None and years > hi:
        return cfg.overqualified_fit
    return 1.0


def location_fit(
    jd: JobDescription, profile: ProfileFacts, prefs: Prefs, cfg: ScoringConfig
) -> float:
    if jd.work_mode == "remote":
        return 1.0 if prefs.open_to_remote else 0.0
    cities = [c.lower() for c in prefs.cities] or (
        [profile.location.lower()] if profile.location else []
    )
    if not jd.location or not cities:
        return cfg.neutral_fit
    jd_loc = jd.location.lower()
    return 1.0 if any(c in jd_loc or jd_loc in c for c in cities) else 0.0


def ctc_fit(jd: JobDescription, prefs: Prefs, cfg: ScoringConfig) -> float:
    top = jd.ctc_lpa_max if jd.ctc_lpa_max is not None else jd.ctc_lpa_min
    if top is None or prefs.expected_ctc_lpa is None:
        return cfg.neutral_fit
    if prefs.expected_ctc_lpa <= top:
        return 1.0
    return 0.5 if prefs.expected_ctc_lpa <= top * 1.2 else 0.0


def _coverage(musts: list[Must], cfg: ScoringConfig, *, ask: bool) -> float:
    if not musts:
        return 1.0
    credit = {"have": 1.0, "ask": cfg.ask_credit if ask else 0.0}
    return sum(credit.get(m.status, 0.0) for m in musts) / len(musts)


def score_job(
    jd: JobDescription,
    profile: ProfileFacts | None,
    answers: dict[str, str],
    find_evidence: EvidenceFinder,
    cfg: ScoringConfig,
    prefs: Prefs | None = None,
) -> ScoreResult:
    prefs = prefs or Prefs()
    if profile is None:
        musts = [Must(skill=s, status="unknown") for s in jd.must_have]
        return ScoreResult(None, {"reason": "no_approved_profile"}, musts)

    musts = [classify(s, profile, answers, find_evidence, cfg) for s in jd.must_have]
    nice = [classify(s, profile, answers, find_evidence, cfg) for s in jd.nice_to_have]

    parts = {
        "must_coverage": _coverage(musts, cfg, ask=True),
        "experience_fit": experience_fit(jd, profile.years_experience, cfg),
        "location_fit": location_fit(jd, profile, prefs, cfg),
        "ctc_fit": ctc_fit(jd, prefs, cfg),
        "nice_to_have_coverage": _coverage(nice, cfg, ask=False) if nice else 0.0,
    }
    weights = {
        "must_coverage": cfg.w_must,
        "experience_fit": cfg.w_experience,
        "location_fit": cfg.w_location,
        "ctc_fit": cfg.w_ctc,
        "nice_to_have_coverage": cfg.w_nice,
    }
    # Half-up (Python's round() is half-to-even: 62.5 -> 62).
    total = math.floor(100 * sum(weights[k] * parts[k] for k in parts) + 0.5)
    breakdown = {
        k: {"value": round(parts[k], 4), "weight": weights[k]} for k in parts
    } | {"total": total}
    return ScoreResult(total, breakdown, musts)


def musts_summary(musts: list[dict]) -> str | None:
    if not musts:
        return None
    have = sum(1 for m in musts if m.get("status") == "have")
    return f"{have} of {len(musts)}"
