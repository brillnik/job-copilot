"""Gmail reply tracking: connect, sync, classify, move cards.

Privacy: only headers and a short snippet ever reach the classifier, and none of it
is stored or logged. What persists per message is its id, the verdict and the card it
touched. The mailbox address is kept only as a keyed hash.
"""

import base64
import binascii
import hashlib
import hmac
import json
import logging
import secrets
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy.exc import IntegrityError

from app.ai.email_classifier import EmailClassifier
from app.ai.errors import TransientError
from app.core import signing
from app.core.config import settings
from app.core.exceptions import (
    AppError,
    Conflict,
    ExtractionFailed,
    ExtractionUnavailable,
    Forbidden,
    NotFound,
)
from app.models.email import ACCEPTED, DISMISSED, PENDING, EmailEvent, GmailConnection
from app.models.tracker import COLUMNS
from app.repositories.manager import RepositoryManager
from app.schemas.gmail import ConnectedOut, ConnectOut, GmailStatus, Suggestion
from app.schemas.tracker import TrackerPatch
from app.services import crypto
from app.services.email_filter import Candidate, prefilter
from app.services.google import (
    GoogleAuthError,
    GoogleClient,
    GoogleError,
    HistoryExpired,
    authorize_url,
)
from app.services.tracker import TrackerService
from app.tasks.queue import TaskQueue

log = logging.getLogger(__name__)

RANK = {c: i for i, c in enumerate(COLUMNS)}
TARGET = {
    "interview": "interview",
    "rejection": "rejected",
    "recruiter_reply": "response",
    "assessment": "response",
    "offer": "offer",
}


class FeatureDisabled(Forbidden):
    code = "feature_disabled"
    detail = "Gmail tracking is not enabled for this account"


class InvalidState(AppError):
    code = "invalid_state"
    detail = "This sign-in link is invalid or has expired"


class NotConfigured(AppError):
    status_code = 503
    code = "gmail_not_configured"
    detail = "Gmail integration is not configured"


def gmail_enabled(user_id: uuid.UUID) -> bool:
    return settings.gmail_feature or str(user_id) in settings.gmail_enabled_users


def hash_email(address: str) -> str:
    """Keyed hash so a push can be mapped to a user without storing the address."""
    key = f"gmail-email:{settings.signing_secret}".encode()
    return hmac.new(key, address.strip().lower().encode(), hashlib.sha256).hexdigest()


# --- OAuth state ---------------------------------------------------------------
def _b64(b: bytes) -> str:
    return base64.urlsafe_b64encode(b).decode().rstrip("=")


def _mac(body: str) -> str:
    key = f"gmail-state:{settings.signing_secret}".encode()
    return _b64(hmac.new(key, body.encode(), hashlib.sha256).digest())


def make_state(user_id: uuid.UUID) -> str:
    body = _b64(
        json.dumps(
            {
                "u": str(user_id),
                "exp": int(signing.now()) + settings.gmail_state_ttl_s,
                "n": secrets.token_hex(8),
            },
            separators=(",", ":"),
        ).encode()
    )
    return f"{body}.{_mac(body)}"


def read_state(state: str) -> uuid.UUID:
    body, _, mac = state.partition(".")
    if not body or not hmac.compare_digest(mac, _mac(body)):
        raise InvalidState()
    try:
        claims = json.loads(base64.urlsafe_b64decode(body + "=" * (-len(body) % 4)))
        if claims["exp"] < signing.now():
            raise InvalidState()
        return uuid.UUID(claims["u"])
    except (ValueError, KeyError, TypeError, binascii.Error):
        raise InvalidState() from None


# --- sync ------------------------------------------------------------------------
@dataclass
class SyncResult:
    seen: int = 0
    skipped: int = 0  # known, or not job-related
    classified: int = 0
    moved: int = 0
    suggested: int = 0
    failed: int = 0
    status: str = "ok"  # ok | disabled | not_connected | reauth | error


def _refresh_token(conn: GmailConnection) -> str:
    return crypto.decrypt(conn.token_ciphertext.encode()).decode()


def _move(
    repos: RepositoryManager, user_id: uuid.UUID, card_id: str, column: str
) -> None:
    """Move via TrackerService (history entry, ordering); commits the session."""
    TrackerService(repos).patch(user_id, card_id, TrackerPatch(column=column), None)
    card = repos.tracker.get_for_user(user_id, card_id)
    if card is not None and card.history:
        card.history = [*card.history[:-1], {**card.history[-1], "source": "gmail"}]
        repos.session.commit()


def _new_ids(
    google: GoogleClient, access: str, conn: GmailConnection
) -> tuple[list[str], str | None]:
    if conn.history_id:
        try:
            page = google.list_history(access, conn.history_id)
            return page.ids, page.history_id or conn.history_id
        except HistoryExpired:
            log.info("gmail history expired user=%s", conn.user_id)
    # Read the cursor first, so mail arriving while we list is picked up next time.
    cursor = google.profile(access).history_id
    ids = google.list_messages(
        access,
        f"newer_than:{settings.gmail_backfill_days}d",
        settings.gmail_max_messages,
    )
    return ids, cursor


def process_new_messages(
    repos: RepositoryManager,
    google: GoogleClient,
    classifier: EmailClassifier,
    user_id: uuid.UUID,
) -> SyncResult:
    """Idempotent: a message with an event is never classified or moved again, and a
    card never moves backwards, so push + poll running together are safe."""
    res = SyncResult()
    conn = repos.email.connection(user_id)
    if conn is None:
        res.status = "not_connected"
        return res
    if not gmail_enabled(user_id):
        res.status = "disabled"
        return res
    if conn.status != "active":
        res.status = "reauth"
        return res
    try:
        access = google.refresh_access_token(_refresh_token(conn))
    except (GoogleAuthError, ValueError):
        conn.status = "reauth"
        repos.session.commit()
        log.warning("gmail needs reconnect user=%s", user_id)
        res.status = "reauth"
        return res
    except GoogleError as e:
        log.warning("gmail refresh failed user=%s error=%s", user_id, e)
        res.status = "error"
        return res
    try:
        ids, cursor = _new_ids(google, access, conn)
    except GoogleError as e:
        log.warning("gmail list failed user=%s error=%s", user_id, e)
        res.status = "error"
        return res

    known = repos.email.known_message_ids(user_id, ids)
    for mid in ids:
        res.seen += 1
        if mid in known:
            res.skipped += 1
            continue
        try:
            _handle_message(repos, google, classifier, user_id, access, mid, res)
        except (GoogleError, TransientError, ExtractionFailed, ExtractionUnavailable):
            repos.session.rollback()
            res.failed += 1
        except IntegrityError:  # a concurrent run recorded it first
            repos.session.rollback()
            res.skipped += 1
    if res.failed == 0:
        conn = repos.email.connection(user_id)
        if conn is not None:
            conn.history_id = cursor or conn.history_id
            conn.last_synced_at = datetime.now(UTC)
            repos.session.commit()
    else:
        res.status = "error"  # cursor stays put; the batch is retried (dedupe holds)
    log.info(
        "gmail sync user=%s seen=%d classified=%d moved=%d suggested=%d failed=%d",
        user_id, res.seen, res.classified, res.moved, res.suggested, res.failed,
    )  # fmt: skip
    return res


def _handle_message(repos, google, classifier, user_id, access, mid, res) -> None:
    meta = google.get_metadata(access, mid)
    cards = [Candidate(*row) for row in repos.email.watched_cards(user_id)]
    pre = prefilter(
        sender_domain=meta.sender_domain,
        subject=meta.subject,
        snippet=meta.snippet,
        candidates=cards,
        ats_domains=settings.gmail_ats_domains,
    )
    if not pre.passes:
        res.skipped += 1
        return
    cand = pre.candidate
    verdict = classifier.classify(
        subject=meta.subject,
        sender_domain=meta.sender_domain,
        snippet=meta.snippet,
        company=cand.company if cand else None,
        title=cand.title if cand else None,
    )
    res.classified += 1
    event = EmailEvent(
        user_id=user_id,
        gmail_message_id=meta.id,
        job_id=cand.job_id if cand else None,
        classification=verdict.classification,
        confidence=round(verdict.confidence, 3),
        applied_to_tracker=False,
        received_at=meta.received_at,
    )
    target = TARGET.get(verdict.classification)
    forward = bool(cand and target and RANK[target] > RANK.get(cand.column, len(RANK)))
    move = False
    if forward and verdict.confidence >= settings.gmail_auto_threshold:
        event.applied_to_tracker = move = True
    elif forward and verdict.confidence >= settings.gmail_suggest_min:
        event.suggested_column, event.suggestion_status = target, PENDING
        res.suggested += 1
    repos.email.stage_event(event)
    if not move:
        repos.session.commit()
        return
    try:
        _move(repos, user_id, cand.card_id, target)  # commits event + move together
    except NotFound:  # card deleted meanwhile: keep the verdict, move nothing
        repos.session.rollback()
        event.applied_to_tracker = False
        repos.email.stage_event(event)
        repos.session.commit()
        return
    res.moved += 1
    log.info(
        "gmail moved card=%s from=%s to=%s event=%s",
        cand.card_id, cand.column, target, event.id,
    )  # fmt: skip


# --- user-facing ---------------------------------------------------------------
class GmailService:
    def __init__(
        self, repos: RepositoryManager, google: GoogleClient, queue: TaskQueue
    ) -> None:
        self.repos, self.google, self.queue = repos, google, queue

    def _require(self, user_id: uuid.UUID) -> None:
        if not gmail_enabled(user_id):
            raise FeatureDisabled()

    def connect_url(self, user_id: uuid.UUID) -> ConnectOut:
        self._require(user_id)
        if not (settings.google_client_id and settings.gmail_redirect_uri):
            raise NotConfigured()
        return ConnectOut(
            url=authorize_url(
                settings.google_client_id,
                settings.gmail_redirect_uri,
                make_state(user_id),
            )
        )

    def callback(self, code: str | None, state: str, error: str | None) -> ConnectedOut:
        user_id = read_state(state)
        self._require(user_id)
        if error or not code:
            raise AppError("Google sign-in was cancelled", code="gmail_denied")
        if self.repos.users.get(user_id) is None:
            raise NotFound("User not found")
        try:
            tokens = self.google.exchange_code(code)
            profile = self.google.profile(tokens.access_token)
        except GoogleError:
            raise AppError(
                "Could not complete Google sign-in", code="gmail_exchange_failed"
            ) from None
        conn = self.repos.email.connection(user_id)
        if tokens.refresh_token is None and conn is None:
            raise AppError("Google returned no offline access", code="no_refresh_token")
        cipher = (
            crypto.encrypt(tokens.refresh_token.encode()).decode()
            if tokens.refresh_token
            else None
        )
        if conn is None:
            conn = self.repos.email.stage_connection(
                GmailConnection(
                    user_id=user_id, token_ciphertext=cipher or "", email_hash=""
                )
            )
        if cipher:
            conn.token_ciphertext = cipher
        conn.email_hash = hash_email(profile.email)
        conn.status = "active"
        conn.history_id = None  # first sync backfills a few days, then follows history
        conn.connected_at = datetime.now(UTC)
        self.repos.session.commit()
        if settings.gmail_pubsub_topic:
            try:
                self.google.watch(tokens.access_token, settings.gmail_pubsub_topic)
            except GoogleError:
                log.warning("gmail watch failed user=%s (polling covers it)", user_id)
        self.queue.enqueue("poll_gmail", user_id=str(user_id))
        log.info("gmail connected user=%s", user_id)
        return ConnectedOut()

    def disconnect(self, user_id: uuid.UUID) -> None:
        self._require(user_id)
        conn = self.repos.email.connection(user_id)
        if conn is not None:
            try:
                self.google.revoke(_refresh_token(conn))
            except (GoogleError, ValueError):
                # Never block the user's erasure on Google being down.
                log.warning("gmail revoke failed user=%s", user_id)
        self.repos.email.delete_all_for_user(user_id)
        self.repos.session.commit()
        log.info("gmail disconnected user=%s", user_id)

    def status(self, user_id: uuid.UUID) -> GmailStatus:
        if not gmail_enabled(user_id):
            return GmailStatus(enabled=False, connected=False)
        conn = self.repos.email.connection(user_id)
        return GmailStatus(
            enabled=True,
            connected=conn is not None,
            needs_reconnect=bool(conn and conn.status != "active"),
            connected_at=conn.connected_at if conn else None,
            last_synced_at=conn.last_synced_at if conn else None,
            pending_suggestions=self.repos.email.pending_count(user_id),
        )

    def suggestions(self, user_id: uuid.UUID) -> list[Suggestion]:
        self._require(user_id)
        return self._to_schema(self.repos.email.suggestions(user_id))

    def _own_suggestion(self, user_id: uuid.UUID, event_id: str) -> EmailEvent:
        self._require(user_id)
        event = self.repos.email.event(user_id, event_id)
        if event is None or event.suggestion_status is None:
            raise NotFound("Suggestion not found")
        return event

    def accept(self, user_id: uuid.UUID, event_id: str) -> Suggestion:
        event = self._own_suggestion(user_id, event_id)
        if event.suggestion_status == DISMISSED:
            raise Conflict("This suggestion was dismissed", code="already_resolved")
        if event.suggestion_status == PENDING:
            card = event.job_id and self.repos.tracker.by_job(user_id, event.job_id)
            if not card:
                raise NotFound("Card not found")
            event.suggestion_status = ACCEPTED
            event.resolved_at = datetime.now(UTC)
            if card.column != event.suggested_column:
                event.applied_to_tracker = True
                _move(self.repos, user_id, card.id, event.suggested_column)
            else:
                self.repos.session.commit()
        return self._one(user_id, event.id)

    def dismiss(self, user_id: uuid.UUID, event_id: str) -> Suggestion:
        event = self._own_suggestion(user_id, event_id)
        if event.suggestion_status == ACCEPTED:
            raise Conflict("This suggestion was accepted", code="already_resolved")
        if event.suggestion_status == PENDING:
            event.suggestion_status = DISMISSED
            event.resolved_at = datetime.now(UTC)
            self.repos.session.commit()
        return self._one(user_id, event.id)

    def _one(self, user_id: uuid.UUID, event_id: str) -> Suggestion:
        rows = self.repos.email.suggestions(user_id, status=None)
        return next(s for s in self._to_schema(rows) if s.id == event_id)

    @staticmethod
    def _to_schema(rows) -> list[Suggestion]:
        return [
            Suggestion(
                id=e.id, job_id=e.job_id, company=c, title=t,
                classification=e.classification, confidence=e.confidence,
                suggested_column=e.suggested_column,  # type: ignore[arg-type]
                status=e.suggestion_status,  # type: ignore[arg-type]
                received_at=e.received_at,
            )
            for e, c, t in rows
        ]  # fmt: skip

    # --- Pub/Sub push ----------------------------------------------------------
    def push(self, token: str | None, data_b64: str) -> None:
        secret = settings.gmail_push_secret
        if not secret or not token or not hmac.compare_digest(token, secret):
            raise Forbidden("Invalid push token")
        try:
            data = json.loads(base64.b64decode(data_b64 + "=" * (-len(data_b64) % 4)))
            address = str(data["emailAddress"])
        except (ValueError, KeyError, TypeError, binascii.Error):
            return  # malformed: ack so Pub/Sub does not redeliver forever
        conn = self.repos.email.connection_by_hash(hash_email(address))
        if conn is None:
            return  # unknown mailbox: ack silently, reveal nothing
        self.queue.enqueue("poll_gmail", user_id=str(conn.user_id))
