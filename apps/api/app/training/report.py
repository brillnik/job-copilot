"""Shadow report: how the local extractor compares with Claude.

    python -m app.training.report [--kind profile|jd] [--json]

Reads extractor_shadow_runs (booleans and counts only) and prints, per slice and
overall: schema validity, hallucination rate and per-field precision/recall/F1
(Claude's output is the reference).
"""

import argparse
import json
from collections.abc import Iterable
from typing import Any


def prf(tp: int, fp: int, fn: int) -> dict[str, float]:
    p = tp / (tp + fp) if tp + fp else 1.0 if fn == 0 else 0.0
    r = tp / (tp + fn) if tp + fn else 1.0 if fp == 0 else 0.0
    f1 = 2 * p * r / (p + r) if p + r else 0.0
    return {"precision": round(p, 4), "recall": round(r, 4), "f1": round(f1, 4)}


def _summarise(rows: list[dict[str, Any]]) -> dict[str, Any]:
    usable = [r for r in rows if not r.get("local_error")]
    valid = [r for r in usable if r.get("schema_valid")]
    totals: dict[str, list[int]] = {}
    matches: dict[str, list[int]] = {}
    for r in valid:
        for name, f in r["fields"].items():
            t = totals.setdefault(name, [0, 0, 0])
            t[0] += f["tp"]
            t[1] += f["fp"]
            t[2] += f["fn"]
            m = matches.setdefault(name, [0, 0])
            m[0] += bool(f["match"])
            m[1] += 1
    emitted = sum(r.get("emitted", 0) for r in valid)
    hallucinated = sum(r.get("hallucinated", 0) for r in valid)
    fields = {
        name: {
            **prf(*t),
            "exact_match_rate": round(matches[name][0] / matches[name][1], 4),
        }
        for name, t in sorted(totals.items())
    }
    all_t = [sum(t[i] for t in totals.values()) for i in range(3)]
    return {
        "runs": len(rows),
        "local_errors": len(rows) - len(usable),
        "schema_validity": round(len(valid) / len(usable), 4) if usable else None,
        "hallucination_rate": round(hallucinated / emitted, 4) if emitted else 0.0,
        "micro": prf(*all_t),
        "fields": fields,
    }


def compute_report(rows: Iterable[tuple[str, str, dict[str, Any]]]) -> dict[str, Any]:
    """rows: (kind, slice, results). Returns {kind: {slice | "ALL": summary}}."""
    grouped: dict[str, dict[str, list[dict[str, Any]]]] = {}
    for kind, slice_, results in rows:
        by = grouped.setdefault(kind, {})
        by.setdefault(slice_, []).append(results)
        by.setdefault("ALL", []).append(results)
    return {
        kind: {s: _summarise(rs) for s, rs in sorted(by.items())}
        for kind, by in sorted(grouped.items())
    }


def load_rows(session, kind: str | None = None):
    from sqlalchemy import select

    from app.models.training import ExtractorShadowRun as R

    stmt = select(R.kind, R.slice, R.results)
    if kind:
        stmt = stmt.where(R.kind == kind)
    return [(k, s, r) for k, s, r in session.execute(stmt)]


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(prog="python -m app.training.report")
    ap.add_argument("--kind", choices=["profile", "jd"])
    args = ap.parse_args(argv)
    from app.db.session import SessionLocal

    with SessionLocal() as session:
        report = compute_report(load_rows(session, args.kind))
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
