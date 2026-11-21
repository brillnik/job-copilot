import pytest
from fastapi.testclient import TestClient

from app.ai.embeddings import HashingEmbedder
from app.core.security import token_claims
from app.main import app
from app.models.screening import ScreeningAnswer
from app.repositories.manager import RepositoryManager
from app.schemas.job import JobDescription
from app.schemas.profile import Bullet, Contact, Experience, ProfileData
from app.schemas.screening import ScreeningField
from app.services.screening import ScreeningService
from tests.jobs_helpers import approve_profile, make_user

PROFILE = ProfileData(
    contact=Contact(
        name="Ada",
        links=["https://github.com/ada", "https://linkedin.com/in/ada"],
    ),
    skills=["Python", "Postgres"],
    experience=[
        Experience(
            id="e1", company="Acme", title="Engineer", start="2020-01", end="2022-01",
            bullets=[Bullet(id="b1", text="Built Python services on Postgres")],
        ),
        Experience(
            id="e2", company="Initech", title="Dev", start="2022-01", end="2023-01",
            bullets=[Bullet(id="b2", text="More Python and Postgres work")],
        ),
    ],
)  # fmt: skip
JOB = JobDescription(title="Backend", location="Bengaluru", must_have=["Python"])


class FakeDraftLLM:
    def __init__(self, text=None, error=None):
        self.text, self.error, self.calls = text, error, 0

    def draft(self, question, profile, jd):
        self.calls += 1
        if self.error:
            raise self.error
        return self.text


@pytest.fixture
def user(db_session):
    u = make_user(db_session)
    approve_profile(db_session, u, PROFILE)
    return u


def svc(db, llm=None):
    return ScreeningService(RepositoryManager(db), HashingEmbedder(), llm)


def f(label, t="other", **kw):
    return ScreeningField(label=label, field_type=t, **kw)


def set_prefs(db, user, **prefs):
    user.preferences = prefs
    db.commit()


# --- structured --------------------------------------------------------------
def test_notice_and_ctc_come_from_settings(db_session, user):
    set_prefs(
        db_session, user, notice_days=30, current_ctc_lpa=18, expected_ctc_lpa=25.5
    )
    s = svc(db_session)
    assert s.answer_for(user.id, f("Notice period?", "notice_period"), JOB) == {
        "value": "30 days", "source": "settings"}  # fmt: skip
    assert s.answer_for(user.id, f("Current CTC", "current_ctc"), JOB)["value"] == "18"
    assert (
        s.answer_for(user.id, f("Expected CTC", "expected_ctc"), JOB)["value"] == "25.5"
    )


def test_unset_settings_are_never_guessed(db_session, user):
    s = svc(db_session)  # user never saved preferences
    for t in ("notice_period", "current_ctc", "expected_ctc"):
        assert s.answer_for(user.id, f("q", t), JOB) is None


def test_relocation_from_preferred_cities(db_session, user):
    set_prefs(db_session, user, cities=["Bengaluru"])
    s = svc(db_session)
    got = s.answer_for(user.id, f("Open to relocate?", "relocation"), JOB)
    assert got == {"value": "Yes", "source": "settings"}
    pune = JobDescription(location="Pune")
    assert s.answer_for(user.id, f("Open to relocate?", "relocation"), pune) is None


def test_years_with_a_tool_from_the_profile(db_session, user):
    got = svc(db_session).answer_for(
        user.id, f("Years of Python?", "years_experience", tool="Python"), JOB
    )
    assert got == {"value": "3", "source": "profile"}
    assert (
        svc(db_session).answer_for(
            user.id, f("Years of Rust?", "years_experience", tool="Rust"), JOB
        )
        is None
    )  # factual, no source


def test_links_from_the_profile(db_session, user):
    got = svc(db_session).answer_for(
        user.id, f("GitHub", "link", link_kind="github"), JOB
    )
    assert got == {"value": "https://github.com/ada", "source": "profile"}
    assert (
        svc(db_session).answer_for(
            user.id, f("Site", "link", link_kind="portfolio"), JOB
        )
        is None
    )


# --- saved answers ----------------------------------------------------------
def test_saved_answer_by_meaning_same_field_type_only(db_session, user):
    s = svc(db_session)
    s.remember(
        user.id,
        "Are you legally authorised to work in India?",
        "Yes",
        "work_authorization",
    )
    same = s.answer_for(
        user.id,
        f("Are you legally authorised to work in India", "work_authorization"),
        JOB,
    )
    assert same == {"value": "Yes", "source": "saved"}
    # same words, different field type: not reused
    assert (
        s.answer_for(
            user.id, f("Are you legally authorised to work in India?", "other"), JOB
        )
        is None
    )
    # unrelated question of the same type: below the similarity bar
    assert (
        s.answer_for(
            user.id,
            f("Do you need a visa sponsorship for Germany", "work_authorization"),
            JOB,
        )
        is None
    )


def test_saved_answers_are_per_user(db_session, user):
    other = make_user(db_session, "auth0|B")
    svc(db_session).remember(
        other.id, "Work authorisation status", "Yes", "work_authorization"
    )
    assert (
        svc(db_session).answer_for(
            user.id, f("Work authorisation status", "work_authorization"), JOB
        )
        is None
    )


def test_remember_updates_in_place(db_session, user):
    s = svc(db_session)
    a = s.remember(user.id, "Why us?", "one", "open")
    b = s.remember(user.id, "why us", "two", "open", "approved_apply")
    assert a.id == b.id and b.answer == "two" and b.source == "approved_apply"


# --- open questions ------------------------------------------------------------
def test_open_question_drafted_and_fact_checked(db_session, user):
    llm = FakeDraftLLM("I enjoy building Python services on Postgres.")
    got = svc(db_session, llm).answer_for(
        user.id, f("Why do you want this role?", "open"), JOB
    )
    assert got == {
        "value": "I enjoy building Python services on Postgres.",
        "source": "drafted",
    }


def test_open_question_with_an_unsupported_claim_fails_fact_check(db_session, user):
    for text in (
        "I scaled Kubernetes clusters for years",  # tool not in profile
        "I cut costs by 40% with Python",  # number not in profile
    ):
        llm = FakeDraftLLM(text)
        assert (
            svc(db_session, llm).answer_for(
                user.id, f("Tell us about yourself", "open"), JOB
            )
            is None
        )
        assert llm.calls == 1


def test_open_question_without_llm_or_on_llm_failure_is_none(db_session, user):
    assert svc(db_session).answer_for(user.id, f("Why us?", "open"), JOB) is None
    llm = FakeDraftLLM(error=RuntimeError("down"))
    assert svc(db_session, llm).answer_for(user.id, f("Why us?", "open"), JOB) is None
    assert (
        svc(db_session, FakeDraftLLM("  ")).answer_for(
            user.id, f("Why us?", "open"), JOB
        )
        is None
    )


def test_open_question_prefers_a_saved_answer(db_session, user):
    s = svc(db_session, FakeDraftLLM("drafted"))
    s.remember(user.id, "Why do you want to join us?", "My own words", "open")
    got = s.answer_for(user.id, f("Why do you want to join us?", "open"), JOB)
    assert got == {"value": "My own words", "source": "saved"}


def test_factual_with_no_source_is_none_and_never_drafted(db_session, user):
    llm = FakeDraftLLM("Yes")
    assert (
        svc(db_session, llm).answer_for(
            user.id, f("Do you hold a security clearance?", "other"), JOB
        )
        is None
    )
    assert llm.calls == 0


def test_no_approved_profile_means_no_profile_answers(db_session):
    u = make_user(db_session, "auth0|Z")
    assert (
        svc(db_session, FakeDraftLLM("x")).answer_for(u.id, f("Why?", "open"), JOB)
        is None
    )


# --- endpoints -----------------------------------------------------------------
client = TestClient(app)


@pytest.fixture
def auth():
    app.dependency_overrides[token_claims] = lambda: {"sub": "auth0|A"}


def test_endpoints_list_put_delete(db_session, user, auth):
    row = svc(db_session).remember(user.id, "Why us?", "old", "open", "approved_apply")
    r = client.get("/screening-answers")
    assert r.status_code == 200
    (item,) = r.json()["items"]
    assert item["id"] == row.id and item["answer"] == "old" and "embedding" not in item
    r = client.put(
        f"/screening-answers/{row.id}",
        json={"answer": "new", "question": "Why join us?"},
    )
    assert (
        r.status_code == 200
        and r.json()["answer"] == "new"
        and r.json()["source"] == "user"
    )
    db_session.refresh(row)
    assert row.normalised_question == "why join us"
    assert (
        client.put(f"/screening-answers/{row.id}", json={"answer": ""}).status_code
        == 422
    )
    assert client.delete(f"/screening-answers/{row.id}").status_code == 204
    assert client.get("/screening-answers").json()["items"] == []


def test_other_users_answers_are_404(db_session, user, auth):
    other = make_user(db_session, "auth0|B")
    theirs = svc(db_session).remember(other.id, "Q", "A", "open")
    assert client.get("/screening-answers").json()["items"] == []
    r = client.put(f"/screening-answers/{theirs.id}", json={"answer": "hijack"})
    assert r.status_code == 404 and r.json()["code"] == "not_found"
    assert client.delete(f"/screening-answers/{theirs.id}").status_code == 404
    db_session.refresh(theirs)
    assert theirs.answer == "A"
    assert db_session.get(ScreeningAnswer, theirs.id) is not None
