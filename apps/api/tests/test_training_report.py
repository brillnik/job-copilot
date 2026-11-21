from app.ai.local import Outcome
from app.ai.shadow_diff import diff_results
from app.schemas.profile import ProfileData
from app.training.report import compute_report, prf


def test_prf():
    assert prf(2, 0, 0) == {"precision": 1.0, "recall": 1.0, "f1": 1.0}
    r = prf(1, 1, 3)
    assert r["precision"] == 0.5 and r["recall"] == 0.25 and r["f1"] == 0.3333
    assert prf(0, 0, 0)["f1"] == 1.0 and prf(0, 2, 0)["f1"] == 0.0


def row(valid=True, tp=1, fp=0, fn=0, emitted=10, hallu=0, err=False):
    if err:
        return {"local_error": True, "schema_valid": False, "fields": {}}
    if not valid:
        return {"local_error": False, "schema_valid": False, "fields": {}}
    return {
        "local_error": False,
        "schema_valid": True,
        "emitted": emitted,
        "hallucinated": hallu,
        "fields": {"skills": {"match": fp == fn == 0, "tp": tp, "fp": fp, "fn": fn}},
    }


def test_report_metrics_per_slice():
    rows = [
        ("profile", "pdf", row(tp=3, fp=1, fn=0, emitted=10, hallu=1)),
        ("profile", "pdf", row(valid=False)),
        ("profile", "docx", row(tp=1, fp=0, fn=1)),
        ("profile", "docx", row(err=True)),
        ("jd", "url:short", row()),
    ]
    rep = compute_report(rows)
    pdf = rep["profile"]["pdf"]
    assert pdf["runs"] == 2 and pdf["schema_validity"] == 0.5
    assert pdf["hallucination_rate"] == 0.1
    assert pdf["fields"]["skills"]["precision"] == 0.75
    assert pdf["fields"]["skills"]["exact_match_rate"] == 0.0
    docx = rep["profile"]["docx"]
    assert docx["local_errors"] == 1 and docx["schema_validity"] == 1.0
    assert rep["profile"]["ALL"]["runs"] == 4
    assert rep["jd"]["ALL"]["micro"]["f1"] == 1.0


def test_empty_report():
    assert compute_report([]) == {}


def test_diff_results_counts():
    ref = ProfileData(skills=["a", "b"])
    local = ProfileData(skills=["b", "c"])
    out = diff_results(ref, Outcome(local, local, True, 4, 0))
    assert out["fields"]["skills"] == {"match": False, "tp": 1, "fp": 1, "fn": 1}
    assert diff_results(ref, Outcome(None, None, False))["schema_valid"] is False
