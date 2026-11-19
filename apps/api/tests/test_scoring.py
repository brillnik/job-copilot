import pytest

from app.agent.scoring import (
    Prefs,
    ProfileFacts,
    ScoringConfig,
    classify,
    ctc_fit,
    experience_fit,
    location_fit,
    musts_summary,
    score_job,
)
from app.schemas.job import JobDescription

CFG = ScoringConfig(
    adjacency={"kafka": ["rabbitmq"], "postgresql": ["mysql"]},
    synonyms={"kubernetes": ["k8s"], "postgresql": ["postgres"]},
)


def profile(**kw):
    base = dict(  # noqa: C408
        skills=["Python", "K8s"],
        bullets=[("b1", "Built Kafka pipelines"), ("b2", "Ran RabbitMQ clusters")],
        years_experience=5.0,
        location="Bengaluru",
    )
    return ProfileFacts(**(base | kw))


def nothing(_skill):
    return None


@pytest.mark.parametrize(
    "skill,answers,finder,status,evidence",
    [
        ("Python", {}, nothing, "have", None),
        ("Kubernetes", {}, nothing, "have", None),  # synonym of skills entry K8s
        ("kafka", {}, nothing, "have", "b1"),  # bullet mention gives evidence
        ("Redis", {}, lambda s: ("b9", 0.6), "have", "b9"),  # vector evidence
        ("Redis", {}, lambda s: ("b9", 0.3), "missing", None),  # below threshold
        ("Postgres", {}, nothing, "missing", None),
        ("RabbitMQ", {}, nothing, "have", "b2"),
        ("Go", {"go": "yes"}, nothing, "have", None),
        (
            "Python",
            {"python": "no"},
            nothing,
            "missing",
            None,
        ),  # said no beats the match
        ("kafka", {"kafka": "no"}, nothing, "missing", None),
    ],
)
def test_classify(skill, answers, finder, status, evidence):
    m = classify(skill, profile(), answers, finder, CFG)
    assert (m.status, m.evidence_bullet_id) == (status, evidence)


def test_ask_when_adjacent_skill_present():
    p = profile(skills=["MySQL"], bullets=[])
    assert classify("PostgreSQL", p, {}, nothing, CFG).status == "ask"
    assert classify("Postgres", p, {}, nothing, CFG).status == "ask"  # synonym
    assert (
        classify("PostgreSQL", p, {"postgresql": "no"}, nothing, CFG).status
        == "missing"
    )


def test_adjacent_found_in_bullet_text():
    p = profile(skills=[], bullets=[("b5", "Operated a RabbitMQ cluster")])
    assert classify("Kafka", p, {}, nothing, CFG).status == "ask"


def test_word_boundaries_do_not_false_match():
    p = profile(skills=[], bullets=[("b1", "Used Django and goroutines")])
    assert classify("Go", p, {}, nothing, CFG).status == "missing"
    assert (
        classify(
            "Java",
            profile(skills=[], bullets=[("b", "Wrote JavaScript")]),
            {},
            nothing,
            CFG,
        ).status
        == "missing"
    )


@pytest.mark.parametrize(
    "lo,hi,years,expected",
    [
        (3, 6, 5, 1.0),
        (5, None, 2.5, 0.5),
        (3, 5, 9, 0.8),
        (None, None, 4, 0.5),
        (3, 5, None, 0.5),
    ],
)
def test_experience_fit(lo, hi, years, expected):
    jd = JobDescription(experience_years_min=lo, experience_years_max=hi)
    assert experience_fit(jd, years, CFG) == expected


@pytest.mark.parametrize(
    "mode,loc,expected",
    [
        ("remote", "Pune", 1.0),
        ("onsite", "Bengaluru, India", 1.0),
        ("hybrid", "Mumbai", 0.0),
        ("onsite", None, 0.5),
    ],
)
def test_location_fit(mode, loc, expected):
    jd = JobDescription(work_mode=mode, location=loc)
    assert location_fit(jd, profile(), Prefs(), CFG) == expected


def test_location_unknown_user_is_neutral_and_remote_opt_out():
    jd = JobDescription(work_mode="onsite", location="Pune")
    assert location_fit(jd, profile(location=None), Prefs(), CFG) == 0.5
    assert (
        location_fit(
            JobDescription(work_mode="remote"),
            profile(),
            Prefs(open_to_remote=False),
            CFG,
        )
        == 0.0
    )


@pytest.mark.parametrize(
    "expected,lo,hi,fit",
    [
        (30, 20, 40, 1.0),
        (45, 20, 40, 0.5),
        (60, 20, 40, 0.0),
        (None, 20, 40, 0.5),
        (30, None, None, 0.5),
        (30, 35, None, 1.0),
    ],
)
def test_ctc_fit(expected, lo, hi, fit):
    jd = JobDescription(ctc_lpa_min=lo, ctc_lpa_max=hi)
    assert ctc_fit(jd, Prefs(expected_ctc_lpa=expected), CFG) == fit


def test_weights_and_total():
    jd = JobDescription(
        must_have=[
            "Python",
            "Kafka",
            "Redis",
            "Postgres",
        ],  # have, have, missing, missing
        nice_to_have=["Python", "Go"],  # 1 of 2
        experience_years_min=3,
        experience_years_max=6,
        work_mode="remote",
    )
    r = score_job(jd, profile(), {}, nothing, CFG, Prefs(expected_ctc_lpa=None))
    # must 0.5, exp 1.0, loc 1.0, ctc 0.5 (neutral), nice 0.5
    # 100 * (0.3 + 0.15 + 0.1 + 0.05 + 0.025) = 62.5, rounded half-up
    assert r.score == 63
    assert r.breakdown["total"] == 63
    assert set(r.breakdown) == {
        "must_coverage",
        "experience_fit",
        "location_fit",
        "ctc_fit",
        "nice_to_have_coverage",
        "total",
    }
    assert [m.status for m in r.musts] == ["have", "have", "missing", "missing"]


def test_ask_gets_partial_credit_and_custom_weights():
    cfg = ScoringConfig(
        w_must=1.0,
        w_experience=0,
        w_location=0,
        w_ctc=0,
        w_nice=0,
        adjacency={"postgresql": ["mysql"]},
    )
    jd = JobDescription(must_have=["PostgreSQL"])
    r = score_job(jd, profile(skills=["MySQL"], bullets=[]), {}, nothing, cfg)
    assert r.score == 50


def test_no_profile_gives_null_score_and_unknown_musts():
    r = score_job(JobDescription(must_have=["Python", "Go"]), None, {}, nothing, CFG)
    assert r.score is None
    assert [m.status for m in r.musts] == ["unknown", "unknown"]


def test_no_musts_counts_as_full_coverage():
    r = score_job(JobDescription(), profile(), {}, nothing, CFG)
    assert r.breakdown["must_coverage"]["value"] == 1.0


def test_musts_summary():
    assert (
        musts_summary([{"status": "have"}, {"status": "ask"}, {"status": "have"}])
        == "2 of 3"
    )
    assert musts_summary([]) is None
