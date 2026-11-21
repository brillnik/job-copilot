"""PII scrubber for training records.

Replaces names, emails, phones, links and the candidate's residence with consistent
fakes. Deterministic per record: the same original value always maps to the same
fake within one Scrubber (seeded per record), so the text and its gold JSON stay
consistent with each other. Conservative by design: it also masks anything that
merely looks like an email, phone number or URL.

Bump SCRUB_VERSION whenever behaviour changes; it goes into the snapshot manifest.
"""

import hashlib
import re
from collections.abc import Iterable
from typing import Any

SCRUB_VERSION = "scrub-v1"

_FIRST = [
    "Alex",
    "Sam",
    "Jordan",
    "Taylor",
    "Morgan",
    "Casey",
    "Riley",
    "Jamie",
    "Robin",
    "Avery",
    "Quinn",
    "Devon",
    "Kai",
    "Rowan",
    "Sage",
    "Reese",
    "Emery",
    "Harper",
    "Blake",
    "Dana",
]
_LAST = [
    "Rivera",
    "Hayes",
    "Brooks",
    "Ellis",
    "Foster",
    "Grant",
    "Holt",
    "Keane",
    "Lowe",
    "Marsh",
    "Nash",
    "Pryor",
    "Reed",
    "Shaw",
    "Stone",
    "Tate",
    "Vance",
    "Ward",
    "Yates",
    "Zane",
]
_CITIES = [
    "Springfield",
    "Riverton",
    "Lakeside",
    "Fairview",
    "Georgetown",
    "Madison",
    "Clinton",
    "Franklin",
    "Ashland",
    "Oxford",
    "Salem",
    "Dover",
]

_EMAIL = re.compile(r"[\w.+%-]+@[\w-]+(?:\.[\w-]+)+")
_URL = re.compile(
    r"(?:https?://|www\.)[^\s<>\"')\]]+"
    r"|(?:linkedin\.com|github\.com|gitlab\.com|bitbucket\.org|twitter\.com|x\.com)"
    r"/[^\s<>\"')\]]+",
    re.IGNORECASE,
)
_PHONE = re.compile(r"(?<![\w.])\+?\d[\d\s().-]{7,}\d(?![\w])")


def _h(*parts: str) -> int:
    return int.from_bytes(
        hashlib.sha256("\x1f".join(parts).encode()).digest()[:8], "big"
    )


def _hex(*parts: str) -> str:
    return hashlib.sha256("\x1f".join(parts).encode()).hexdigest()[:10]


class Scrubber:
    def __init__(
        self,
        seed: str,
        names: Iterable[str] = (),
        emails: Iterable[str] = (),
        phones: Iterable[str] = (),
        links: Iterable[str] = (),
        locations: Iterable[str] = (),
    ) -> None:
        self.seed = seed
        known: dict[str, str] = {}  # lowercased original -> fake
        for full in names:
            for tok in re.findall(r"[^\W\d_]{3,}", full or ""):
                known[tok.casefold()] = self._name(tok)
        for email in emails:
            if email and email.strip():
                known[email.strip().casefold()] = self._email(email.strip())
        for phone in phones:
            if phone and phone.strip():
                known[phone.strip().casefold()] = self._phone(phone.strip())
        for link in links:
            if link and link.strip():
                known[link.strip().casefold()] = self._url(link.strip())
        for loc in locations:
            parts = [p.strip() for p in (loc or "").split(",") if p.strip()]
            if parts:
                known[loc.strip().casefold()] = self._city(parts[0])
                if len(parts[0]) >= 4:
                    known[parts[0].casefold()] = self._city(parts[0])
        self._known = known
        self._known_re = (
            re.compile(
                "|".join(
                    rf"(?<!\w){re.escape(k)}(?!\w)"
                    for k in sorted(known, key=len, reverse=True)
                ),
                re.IGNORECASE,
            )
            if known
            else None
        )

    # --- fakes ---------------------------------------------------------------
    def _name(self, tok: str) -> str:
        n = _h(self.seed, "name", tok.casefold())
        pool = _FIRST if n % 2 == 0 else _LAST
        return pool[(n >> 8) % len(pool)]

    def _city(self, v: str) -> str:
        return _CITIES[_h(self.seed, "city", v.casefold()) % len(_CITIES)]

    def _email(self, v: str) -> str:
        return f"user{_hex(self.seed, 'email', v.casefold())[:8]}@example.com"

    def _url(self, v: str) -> str:
        core = re.sub(
            r"^(?:https?://)?(?:www\.)?",
            "",
            v.strip().rstrip("/.,;"),
            flags=re.IGNORECASE,
        )
        fake = f"example.com/u/{_hex(self.seed, 'url', core.casefold())[:8]}"
        return f"https://{fake}" if re.match(r"https?://", v, re.IGNORECASE) else fake

    def _phone(self, v: str) -> str:
        digits = re.sub(r"\D", "", v)
        stream = _hex(self.seed, "phone", digits) + _hex(self.seed, "phone2", digits)
        # Keep a leading country code ("+91") so the fake still looks like a phone.
        keep = m.group(0) if (m := re.match(r"\s*\+\d{1,3}(?=\D)", v)) else ""
        out, i = [keep], 0
        for ch in v[len(keep) :]:
            if ch.isdigit():
                d = int(stream[i % len(stream)], 16) % 10
                out.append(str(d))
                i += 1
            else:
                out.append(ch)
        return "".join(out)

    # --- scrubbing -----------------------------------------------------------
    def text(self, s: str) -> str:
        if not s:
            return s
        if self._known_re is not None:
            s = self._known_re.sub(lambda m: self._known[m.group(0).casefold()], s)
        s = _EMAIL.sub(lambda m: self._email(m.group(0)), s)
        s = _URL.sub(self._url_sub, s)
        return _PHONE.sub(self._phone_sub, s)

    def _url_sub(self, m: re.Match) -> str:
        raw = m.group(0)
        trail = ""
        while raw and raw[-1] in ".,;:!?":
            trail, raw = raw[-1] + trail, raw[:-1]
        return self._url(raw) + trail

    def _phone_sub(self, m: re.Match) -> str:
        raw = m.group(0)
        n = len(re.sub(r"\D", "", raw))
        if n < 10 and not raw.startswith("+"):
            return raw  # a year range or a number, not a phone
        if n > 15 or n < 8:
            return raw
        if re.fullmatch(r"(?:(?:19|20)\d\d[\s-]*)+", raw.strip()):
            return raw  # a run of years, e.g. "2019 - 2021 2022"
        return self._phone(raw)

    def obj(self, value: Any) -> Any:
        if isinstance(value, str):
            return self.text(value)
        if isinstance(value, list):
            return [self.obj(v) for v in value]
        if isinstance(value, dict):
            return {k: self.obj(v) for k, v in value.items()}
        return value


def strip_ids(value: Any) -> Any:
    """Drop server-generated `id` and `source_url` keys from gold JSON."""
    if isinstance(value, list):
        return [strip_ids(v) for v in value]
    if isinstance(value, dict):
        return {
            k: strip_ids(v) for k, v in value.items() if k not in ("id", "source_url")
        }
    return value
