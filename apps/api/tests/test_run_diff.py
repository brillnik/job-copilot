import itertools

import pytest

from app.agent.diff import word_diff
from app.agent.fact_check import build_facts, fact_check
from app.core.config import settings
from app.schemas.profile import Bullet, Experience, ProfileData
from app.schemas.run import TailoredBullet, TailoredResume

OLD = "Built Kafka pipelines processing 2M events a day"


def rebuild(segs, ops):
    return "".join(s.text for s in segs if s.op in ops)


@pytest.mark.parametrize(
    "new",
    [
        OLD,
        "Built Kafka pipelines handling 2M events a day",
        "Designed and built Kafka pipelines processing 2M events a day",
        "Kafka pipelines",
        "",
        "Totally different sentence",
    ],
)
def test_diff_round_trips(new):
    segs = word_diff(OLD, new)
    assert rebuild(segs, {"same", "del"}) == OLD
    assert rebuild(segs, {"same", "add"}) == new
    assert all(a.op != b.op for a, b in itertools.pairwise(segs))  # runs are merged


def test_same_add_del_segments():
    assert [(s.op, s.text) for s in word_diff(OLD, OLD)] == [("same", OLD)]
    segs = word_diff(OLD, "Built Kafka pipelines handling 2M events a day")
    assert [(s.op, s.text) for s in segs] == [
        ("same", "Built Kafka pipelines "),
        ("del", "processing"),
        ("add", "handling"),
        ("same", " 2M events a day"),
    ]
    assert [(s.op, s.text) for s in word_diff("a b", "a b c")] == [
        ("same", "a b"),
        ("add", " c"),
    ]
    assert [(s.op, s.text) for s in word_diff("a b c", "a c")] == [
        ("same", "a "), ("del", "b "), ("same", "c"),
    ]  # fmt: skip


PROFILE = ProfileData(
    skills=["Python", "Postgres"],
    summary="Backend engineer",
    experience=[
        Experience(
            id="e1",
            company="Acme",
            bullets=[
                Bullet(id="b1", text="Built APIs in Python serving 40% more traffic")
            ],
        )
    ],
)


def violations(resume, answers=()):
    return {
        (v.code, v.term)
        for v in fact_check(
            build_facts(PROFILE, list(answers), synonyms=settings.skill_synonyms),
            resume,
        )
    }


def bullet(text):
    return TailoredResume(bullets=[TailoredBullet(source_id="b1", text=text)])


def test_fact_check_catches_invention_and_allows_rewording():
    assert violations(bullet("Built Python APIs that served 40% more traffic")) == set()
    assert violations(bullet("Built Python APIs serving 60% more traffic")) == {
        ("invented_number", "60%")
    }
    assert violations(bullet("Built Python APIs on Kubernetes")) == {
        ("unsupported_skill", "kubernetes")
    }
    assert violations(bullet("Built Python APIs on K8s")) == {
        ("unsupported_skill", "k8s")
    }  # alias
    assert violations(TailoredResume(skills_order=["Python", "Go"])) == {
        ("unsupported_skill", "Go")
    }
    assert violations(TailoredResume(summary="Expert in Kafka")) == {
        ("unsupported_skill", "kafka")
    }
    assert violations(
        TailoredResume(bullets=[TailoredBullet(source_id="nope", text="x")])
    ) == {("unknown_source", None)}


def test_a_bullet_cannot_borrow_a_skill_from_another_part_of_the_profile():
    # Postgres is a profile skill but this bullet never mentioned it
    assert violations(bullet("Built Python APIs backed by Postgres")) == {
        ("unsupported_skill", "postgres")
    }


def test_confirmed_yes_answers_widen_what_is_claimable_no_answers_do_not():
    r = bullet("Built Python APIs on Kubernetes")
    assert violations(r, [("kubernetes", "yes", "ran EKS")]) == set()
    assert violations(r, [("kubernetes", "no", None)]) == {
        ("unsupported_skill", "kubernetes")
    }
