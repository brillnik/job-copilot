import pytest
from sqlalchemy import select

from app.ai.errors import TransientError
from app.core.config import settings
from app.models.email import EmailEvent, GmailConnection
from app.models.tracker import TrackerCard
from app.repositories.manager import RepositoryManager
from app.services import crypto
from app.services.gmail import process_new_messages
from app.services.google import GoogleAuthError, HistoryExpired
from tests.gmail_helpers import (
    EMAIL,
    FakeClassifier,
    FakeGoogle,
    connect_user,
    enable,
    msg,
    seed_card,
)
from tests.jobs_helpers import make_user


def setup(db, monkeypatch, google, **card):
    user, job, card_ = seed_card(db, **card)
    enable(monkeypatch, user)
    connect_user(db, user, google)
    return user, job, card_


def sync(db, google, classifier, user):
    return process_new_messages(RepositoryManager(db), google, classifier, user.id)


def column(db, card):
    return db.scalar(select(TrackerCard.column).where(TrackerCard.id == card.id))


def events(db):
    return db.scalars(select(EmailEvent)).all()


def test_high_confidence_moves_the_card_and_logs_history(db_session, monkeypatch):
    g = FakeGoogle([msg("m1", subject="Interview invite")])
    user, job, card = setup(db_session, monkeypatch, g)
    res = sync(db_session, g, FakeClassifier("interview", 0.95), user)
    assert (res.moved, res.suggested) == (1, 0)
    assert column(db_session, card) == "interview"
    c = db_session.get(TrackerCard, card.id)
    assert c.history[-1]["to"] == "interview" and c.history[-1]["source"] == "gmail"
    (e,) = events(db_session)
    assert e.job_id == job.id and e.applied_to_tracker and e.suggestion_status is None


@pytest.mark.parametrize(
    "label,col",
    [
        ("interview", "interview"),
        ("rejection", "rejected"),
        ("recruiter_reply", "response"),
        ("assessment", "response"),
        ("offer", "offer"),
    ],
)
def test_mapping(db_session, monkeypatch, label, col):
    g = FakeGoogle([msg("m1")])
    user, _, card = setup(db_session, monkeypatch, g)
    sync(db_session, g, FakeClassifier(label, 0.8), user)  # threshold is inclusive
    assert column(db_session, card) == col


def test_low_confidence_makes_a_suggestion_and_does_not_move(db_session, monkeypatch):
    g = FakeGoogle([msg("m1")])
    user, _, card = setup(db_session, monkeypatch, g)
    res = sync(db_session, g, FakeClassifier("offer", 0.79), user)
    assert (res.moved, res.suggested) == (0, 1)
    assert column(db_session, card) == "applied"
    (e,) = events(db_session)
    assert (e.suggestion_status, e.suggested_column, e.applied_to_tracker) == (
        "pending", "offer", False,
    )  # fmt: skip


def test_very_low_confidence_and_other_record_but_suggest_nothing(
    db_session, monkeypatch
):
    g = FakeGoogle([msg("m1"), msg("m2")])
    user, _, card = setup(db_session, monkeypatch, g)
    clf = FakeClassifier("offer", 0.2)
    sync(db_session, g, clf, user)
    g2 = FakeGoogle([msg("m3")])
    sync(db_session, g2, FakeClassifier("other", 0.99), user)
    assert column(db_session, card) == "applied"
    assert all(e.suggestion_status is None for e in events(db_session))
    assert len(events(db_session)) == 3


def test_never_moves_backwards(db_session, monkeypatch):
    g = FakeGoogle([msg("m1")])
    user, _, card = setup(db_session, monkeypatch, g, column="interview")
    sync(db_session, g, FakeClassifier("recruiter_reply", 0.99), user)
    assert column(db_session, card) == "interview"
    (e,) = events(db_session)
    assert not e.applied_to_tracker and e.suggestion_status is None


def test_idempotent_across_repeated_syncs(db_session, monkeypatch):
    g = FakeGoogle([msg("m1")])
    user, _, card = setup(db_session, monkeypatch, g)
    clf = FakeClassifier("interview", 0.95)
    for _ in range(3):  # repeated push/poll notifications
        sync(db_session, g, clf, user)
    assert len(events(db_session)) == 1 and len(clf.calls) == 1
    assert column(db_session, card) == "interview"
    hist = db_session.get(TrackerCard, card.id).history
    assert [h["to"] for h in hist].count("interview") == 1


def test_prefilter_gates_the_llm(db_session, monkeypatch):
    g = FakeGoogle([msg("m1", domain="newsletter.example.org", subject="Deals")])
    user, _, _ = setup(db_session, monkeypatch, g)
    clf = FakeClassifier()
    res = sync(db_session, g, clf, user)
    assert clf.calls == [] and res.skipped == 1 and events(db_session) == []


def test_classifier_sees_subject_domain_snippet_only(db_session, monkeypatch):
    g = FakeGoogle([msg("m1", subject="Hi", snippet="short")])
    user, _, _ = setup(db_session, monkeypatch, g)
    clf = FakeClassifier()
    sync(db_session, g, clf, user)
    assert set(clf.calls[0]) == {
        "subject",
        "sender_domain",
        "snippet",
        "company",
        "title",
    }


def test_no_message_content_is_stored(db_session, monkeypatch):
    g = FakeGoogle([msg("m1", subject="SECRET-SUBJECT", snippet="SECRET-SNIPPET")])
    user, _, _ = setup(db_session, monkeypatch, g)
    sync(db_session, g, FakeClassifier("interview", 0.5), user)
    cols = {c.name for c in EmailEvent.__table__.columns}
    assert not cols & {"body", "subject", "snippet", "sender", "from_addr"}
    dump = db_session.connection().connection.driver_connection.iterdump()
    text = "\n".join(dump)
    assert "SECRET-SUBJECT" not in text and "SECRET-SNIPPET" not in text
    assert EMAIL not in text


def test_token_is_encrypted_at_rest_and_address_only_hashed(db_session, monkeypatch):
    g = FakeGoogle(refresh_token="rt-plain-token")
    setup(db_session, monkeypatch, g)
    conn = db_session.scalar(select(GmailConnection))
    assert "rt-plain-token" not in conn.token_ciphertext
    assert crypto.decrypt(conn.token_ciphertext.encode()) == b"rt-plain-token"
    assert EMAIL not in conn.email_hash and len(conn.email_hash) == 64


def test_history_cursor_advances_and_failure_keeps_it(db_session, monkeypatch):
    g = FakeGoogle([msg("m1"), msg("m2")])
    user, _, _ = setup(db_session, monkeypatch, g)
    g.fail_metadata = {"m2"}
    res = sync(db_session, g, FakeClassifier("interview", 0.95), user)
    assert res.failed == 1 and res.status == "error"
    assert db_session.scalar(select(GmailConnection)).history_id is None
    g.fail_metadata = set()
    clf = FakeClassifier("interview", 0.95)
    res = sync(db_session, g, clf, user)
    assert res.failed == 0 and len(clf.calls) == 1  # m1 was not redone
    assert db_session.scalar(select(GmailConnection)).history_id == "100"
    sync(db_session, g, clf, user)
    assert g.history_calls == ["100"]  # now follows history


def test_expired_history_falls_back_to_listing(db_session, monkeypatch):
    g = FakeGoogle([msg("m1")])
    user, _, card = setup(db_session, monkeypatch, g)
    sync(db_session, g, FakeClassifier("other", 0.9), user)

    def boom(*a):
        raise HistoryExpired()

    g.list_history = boom
    g.add(msg("m2"))
    sync(db_session, g, FakeClassifier("interview", 0.95), user)
    assert column(db_session, card) == "interview"


def test_classifier_outage_is_retried_not_lost(db_session, monkeypatch):
    g = FakeGoogle([msg("m1")])
    user, _, card = setup(db_session, monkeypatch, g)
    res = sync(db_session, g, FakeClassifier(error=TransientError("x")), user)
    assert res.failed == 1 and events(db_session) == []
    sync(db_session, g, FakeClassifier("interview", 0.95), user)
    assert column(db_session, card) == "interview"


def test_revoked_grant_flags_reconnect(db_session, monkeypatch):
    g = FakeGoogle([msg("m1")])
    user, _, _ = setup(db_session, monkeypatch, g)
    g.refresh_error = GoogleAuthError("invalid_grant")
    res = sync(db_session, g, FakeClassifier(), user)
    assert res.status == "reauth"
    assert db_session.scalar(select(GmailConnection)).status == "reauth"
    assert sync(db_session, g, FakeClassifier(), user).status == "reauth"


def test_feature_flag_stops_sync(db_session, monkeypatch):
    g = FakeGoogle([msg("m1")])
    user, _, card = setup(db_session, monkeypatch, g)
    monkeypatch.setattr(settings, "gmail_enabled_users", [])
    assert sync(db_session, g, FakeClassifier(), user).status == "disabled"
    assert column(db_session, card) == "applied"


def test_other_users_cards_are_never_touched(db_session, monkeypatch):
    g = FakeGoogle([msg("m1")])
    user, _, _ = setup(db_session, monkeypatch, g)
    _, _, other_card = seed_card(db_session, make_user(db_session, "auth0|B"))
    sync(db_session, g, FakeClassifier("interview", 0.95), user)
    assert column(db_session, other_card) == "applied"
    assert {e.user_id for e in events(db_session)} == {user.id}


def test_tasks_poll_and_fan_out(db_session, monkeypatch):
    import contextlib

    from app.tasks import gmail as tasks
    from app.tasks.queue import RecordingQueue

    g = FakeGoogle([msg("m1")])
    user, _, card = setup(db_session, monkeypatch, g)
    q = RecordingQueue()
    ctx = tasks.GmailContext(
        lambda: contextlib.nullcontext(db_session), g, FakeClassifier("offer", 0.9), q
    )
    assert tasks.poll_all_gmail(ctx) == 1 and q.names() == ["poll_gmail"]
    tasks.poll_gmail(ctx, str(user.id))
    assert column(db_session, card) == "offer"
