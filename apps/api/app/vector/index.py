"""Vector search over the catalogue. A Protocol plus a brute-force cosine index.

Swap in pgvector/Atlas by implementing VectorIndex; callers only see search().
Vectors are compared by cosine similarity (normalised here, so any scale works).
"""

import math
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any, Protocol


@dataclass(frozen=True)
class SearchFilters:
    """Filter fields: closed_at, first_seen, remote, country_restrictions, city."""

    open_only: bool = True  # closed_at is null
    first_seen_after: datetime | None = None
    # Location gate: a row passes if it is remote (and allowed in `country`) or its
    # city is in `cities`. With no cities given, location does not filter at all.
    cities: tuple[str, ...] = ()
    country: str | None = None


@dataclass(frozen=True)
class Hit:
    id: str
    score: float


@dataclass
class Entry:
    id: str
    vector: list[float]
    fields: dict[str, Any] = field(default_factory=dict)


class VectorIndex(Protocol):
    def upsert(self, id: str, vector: list[float], fields: dict[str, Any]) -> None: ...

    def remove(self, id: str) -> None: ...

    def search(
        self, vector: list[float], k: int, filters: SearchFilters
    ) -> list[Hit]: ...


def _unit(v: list[float]) -> list[float]:
    n = math.sqrt(sum(x * x for x in v))
    return [x / n for x in v] if n else v


def _norm(s: str) -> str:
    return s.strip().lower()


def location_ok(fields: dict[str, Any], f: SearchFilters) -> bool:
    if not f.cities:
        return True
    city = fields.get("city")
    if city and _norm(city) in {_norm(c) for c in f.cities}:
        return True
    if not fields.get("remote"):
        return False
    restrictions = {_norm(c) for c in fields.get("country_restrictions") or []}
    if not restrictions or not f.country:
        return True
    return _norm(f.country) in restrictions or bool(
        restrictions & {"worldwide", "anywhere", "global"}
    )


def matches(fields: dict[str, Any], f: SearchFilters) -> bool:
    if f.open_only and fields.get("closed_at") is not None:
        return False
    first = fields.get("first_seen")
    if f.first_seen_after and (first is None or _cmp(first) < _cmp(f.first_seen_after)):
        return False
    return location_ok(fields, f)


def _cmp(dt: datetime) -> datetime:
    return dt.replace(tzinfo=UTC) if dt.tzinfo is None else dt


class BruteForceIndex:
    """In-memory exact search; fine for the tens of thousands of rows a catalogue holds."""

    def __init__(self) -> None:
        self._rows: dict[str, Entry] = {}

    def __len__(self) -> int:
        return len(self._rows)

    def upsert(self, id: str, vector: list[float], fields: dict[str, Any]) -> None:
        self._rows[id] = Entry(id, _unit(vector), dict(fields))

    def remove(self, id: str) -> None:
        self._rows.pop(id, None)

    def search(self, vector: list[float], k: int, filters: SearchFilters) -> list[Hit]:
        q = _unit(vector)
        hits = [
            Hit(e.id, sum(a * b for a, b in zip(q, e.vector, strict=False)))
            for e in self._rows.values()
            if len(e.vector) == len(q) and matches(e.fields, filters)
        ]
        hits.sort(key=lambda h: (-h.score, h.id))
        return hits[:k]
