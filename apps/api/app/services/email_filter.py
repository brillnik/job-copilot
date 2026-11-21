"""Pure pre-filter: which messages are worth sending to the classifier at all.

A message passes if its sender domain matches an applied company or a known ATS mail
domain, or its subject names an applied role. Only the matching card (if one can be
told apart) is returned, so a reply is never attributed to the wrong application.
"""

import re
from dataclasses import dataclass

PUBLIC_DOMAINS = frozenset(
    {"gmail.com", "googlemail.com", "outlook.com", "hotmail.com", "yahoo.com",
     "yahoo.in", "icloud.com", "proton.me", "protonmail.com", "live.com"}
)  # fmt: skip
SUFFIXES = frozenset(
    {"inc", "ltd", "llc", "llp", "pvt", "private", "limited", "corp", "corporation",
     "co", "gmbh", "plc", "technologies", "technology", "tech", "india", "the"}
)  # fmt: skip
GENERIC_LABELS = frozenset(
    {"mail", "email", "mg", "careers", "jobs", "hire", "recruiting", "talent",
     "notifications", "no-reply", "noreply", "com", "co", "in", "io", "net", "org"}
)  # fmt: skip


@dataclass(frozen=True)
class Candidate:
    card_id: str
    job_id: str
    company: str | None
    title: str | None
    column: str


@dataclass(frozen=True)
class Prefilter:
    passes: bool
    candidate: Candidate | None = None
    reason: str = ""  # "company" | "ats" | "role" | ""


def _alnum(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", text.lower()).strip()


def _company_key(company: str | None) -> str:
    words = [w for w in _alnum(company or "").split() if w not in SUFFIXES]
    return "".join(words)


def _labels(domain: str) -> list[str]:
    parts = [p for p in domain.lower().split(".") if p]
    return [p.replace("-", "") for p in parts if p not in GENERIC_LABELS]


def domain_matches_company(domain: str, company: str | None) -> bool:
    if not domain or domain in PUBLIC_DOMAINS:
        return False
    key = _company_key(company)
    if len(key) < 3:
        return False
    for label in _labels(domain):
        if label == key or (len(key) >= 4 and key in label):
            return True
        if len(label) >= 4 and label in key and len(label) >= len(key) * 0.6:
            return True
    return False


def is_ats_domain(domain: str, ats_domains: list[str] | tuple[str, ...]) -> bool:
    d = domain.lower()
    return any(d == a or d.endswith("." + a) for a in ats_domains)


def subject_names_role(subject: str, title: str | None) -> bool:
    t, s = _alnum(title or ""), _alnum(subject)
    return len(t) >= 8 and " " in t and f" {t} " in f" {s} "


def prefilter(
    *,
    sender_domain: str,
    subject: str,
    snippet: str,
    candidates: list[Candidate],
    ats_domains: list[str] | tuple[str, ...],
) -> Prefilter:
    domain = sender_domain.lower()
    by_company = [c for c in candidates if domain_matches_company(domain, c.company)]
    by_role = [c for c in candidates if subject_names_role(subject, c.title)]
    ats = is_ats_domain(domain, ats_domains)

    if by_company:
        return Prefilter(True, _pick(by_company, subject), "company")
    if ats:
        # An ATS mails for many companies: attribute it only if the text names one.
        text = f" {_alnum(subject + ' ' + snippet)} "
        named = [
            c for c in candidates if len(_company_key(c.company)) >= 3
            and f" {_alnum(c.company or '')} " in text
        ]  # fmt: skip
        return Prefilter(True, _pick(named or by_role, subject), "ats")
    if by_role:
        return Prefilter(True, _pick(by_role, subject), "role")
    return Prefilter(False)


def _pick(cands: list[Candidate], subject: str) -> Candidate | None:
    """One card, or None when several applications at the company are ambiguous."""
    if len(cands) == 1:
        return cands[0]
    titled = [c for c in cands if subject_names_role(subject, c.title)]
    return titled[0] if len(titled) == 1 else None
