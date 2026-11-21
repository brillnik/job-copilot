"""Fakes for Google and the classifier; no network, no LLM."""

import uuid
from datetime import UTC, datetime

from app.ai.email_classifier import EmailClass
from app.core.config import settings
from app.repositories.manager import RepositoryManager
from app.schemas.tracker import TrackerAdd
from app.services.google import (
    GoogleError,
    MailboxProfile,
    MessageIds,
    MessageMeta,
    TokenSet,
)
from app.services.tracker import TrackerService
from tests.jobs_helpers import make_job, make_user

EMAIL = "ada.private@example.com"


def msg(mid, domain="acme.com", subject="Re: your application", snippet=""):
    return MessageMeta(mid, domain, subject, snippet, datetime(2026, 1, 5, tzinfo=UTC))


class FakeGoogle:
    def __init__(self, messages=(), refresh_token="rt-secret", email=EMAIL):
        self.messages = {m.id: m for m in messages}
        self.order = [m.id for m in messages]
        self.refresh_token, self.email = refresh_token, email
        self.revoked: list[str] = []
        self.metadata_calls: list[str] = []
        self.history_calls: list[str] = []
        self.fail_metadata: set[str] = set()
        self.revoke_error: Exception | None = None
        self.refresh_error: Exception | None = None
        self.history_id = "100"

    def add(self, m):
        self.messages[m.id] = m
        self.order.append(m.id)

    def exchange_code(self, code):
        return TokenSet("access-1", self.refresh_token)

    def refresh_access_token(self, refresh_token):
        if self.refresh_error:
            raise self.refresh_error
        assert refresh_token == self.refresh_token
        return "access-2"

    def profile(self, access_token):
        return MailboxProfile(self.email, self.history_id)

    def watch(self, access_token, topic):
        pass

    def list_history(self, access_token, start_history_id):
        self.history_calls.append(start_history_id)
        return MessageIds(list(self.order), self.history_id)

    def list_messages(self, access_token, query, limit):
        return list(self.order)[:limit]

    def get_metadata(self, access_token, message_id):
        self.metadata_calls.append(message_id)
        if message_id in self.fail_metadata:
            raise GoogleError("http_500")
        return self.messages[message_id]

    def revoke(self, token):
        if self.revoke_error:
            raise self.revoke_error
        self.revoked.append(token)


class FakeClassifier:
    def __init__(self, label="interview", confidence=0.95, error=None):
        self.label, self.confidence, self.error = label, confidence, error
        self.calls: list[dict] = []

    def classify(self, **kw):
        self.calls.append(kw)
        if self.error:
            raise self.error
        return EmailClass(classification=self.label, confidence=self.confidence)


def seed_card(
    db,
    user=None,
    company="Acme Technologies Inc",
    title="Senior Backend Engineer",
    column="applied",
):
    user = user or make_user(db)
    job = make_job(db, user, company=company, title=title)
    card = TrackerService(RepositoryManager(db)).add(
        user.id, TrackerAdd(job_id=job.id, column=column)
    )
    return user, job, card


def enable(monkeypatch, *users):
    monkeypatch.setattr(settings, "gmail_enabled_users", [str(u.id) for u in users])


def connect_user(db, user, google):
    """Connect through the real service path so the token is stored encrypted."""
    from app.services.gmail import GmailService, make_state

    svc = GmailService(RepositoryManager(db), google, queue=_NullQueue())
    svc.callback("code", make_state(user.id), None)
    return svc


class _NullQueue:
    def enqueue(self, name, **kw):
        pass


def new_user_id():
    return uuid.uuid4()
