"""Browser-extension pairing, device tokens and clipping. Hashes only are stored."""

import hashlib
import hmac
import logging
import secrets
import threading
import time
import uuid
from datetime import UTC, datetime, timedelta

from app.core.clock import as_utc
from app.core.config import settings
from app.core.exceptions import AppError, NotFound, TooManyRequests, Unauthorized
from app.models.discovery import ExtensionPairingCode, ExtensionToken
from app.models.job import PROCESSING, Job
from app.repositories.manager import RepositoryManager
from app.schemas.extension import ClipIn, PairCodeOut, PairOut
from app.schemas.job import JobAddOut
from app.tasks.jobs import content_hash, normalise_text
from app.tasks.queue import TaskQueue

log = logging.getLogger(__name__)

TOKEN_PREFIX = "jce_"  # never a valid Auth0 JWT, so normal routes reject it outright
_CODE_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"


def digest(secret_value: str) -> str:
    """Keyed hash (HMAC-SHA256) so a leaked table cannot be used to test guesses."""
    return hmac.new(
        settings.signing_secret.encode(), secret_value.encode(), hashlib.sha256
    ).hexdigest()


def _canon_code(code: str) -> str:
    return "".join(ch for ch in code.upper() if ch.isalnum())


class _Throttle:
    """Per-client failed-pairing limiter (in-process; one window per minute)."""

    def __init__(self) -> None:
        self._hits: dict[str, list[float]] = {}
        self._lock = threading.Lock()

    def check(self, key: str) -> None:
        now = time.monotonic()
        with self._lock:
            hits = [t for t in self._hits.get(key, []) if now - t < 60]
            self._hits[key] = hits
            if len(hits) >= settings.extension_pair_attempts_per_min:
                raise TooManyRequests("Too many attempts; try again shortly")

    def fail(self, key: str) -> None:
        with self._lock:
            self._hits.setdefault(key, []).append(time.monotonic())


throttle = _Throttle()


class Invalid(AppError):
    status_code = 422
    code = "validation_error"
    detail = "Invalid input"


class ExtensionService:
    def __init__(self, repos: RepositoryManager, queue: TaskQueue) -> None:
        self.repos, self.queue = repos, queue

    # --- pairing -----------------------------------------------------------
    def new_code(self, user_id: uuid.UUID, now: datetime | None = None) -> PairCodeOut:
        now = now or datetime.now(UTC)
        raw = "".join(secrets.choice(_CODE_ALPHABET) for _ in range(8))
        expires = now + timedelta(seconds=settings.extension_pair_code_ttl_s)
        self.repos.extension.add_code(
            ExtensionPairingCode(
                user_id=user_id, code_hash=digest(raw), expires_at=expires
            )
        )
        log.info("extension pair code issued user=%s", user_id)
        return PairCodeOut(code=f"{raw[:4]}-{raw[4:]}", expires_at=expires)

    def pair(
        self,
        code: str,
        device_name: str | None,
        client: str,
        now: datetime | None = None,
    ) -> PairOut:
        throttle.check(client)
        now = now or datetime.now(UTC)
        user_id = self.repos.extension.consume_code(digest(_canon_code(code)), now)
        if user_id is None:
            throttle.fail(client)
            log.info("extension pairing rejected")
            raise Unauthorized("Invalid or expired code", code="invalid_code")
        token = TOKEN_PREFIX + secrets.token_urlsafe(32)
        row = self.repos.extension.add_token(
            ExtensionToken(
                user_id=user_id, token_hash=digest(token), device_name=device_name
            )
        )
        log.info("extension paired user=%s token=%s", user_id, row.id)
        return PairOut(token_id=row.id, token=token)

    def revoke(self, user_id: uuid.UUID, token_id: str) -> None:
        row = self.repos.extension.token_for_user(user_id, token_id)
        if row is None:
            raise NotFound("Device not found")
        if row.revoked_at is None:
            row.revoked_at = datetime.now(UTC)
            self.repos.session.commit()
        log.info("extension token revoked user=%s token=%s", user_id, row.id)

    def authenticate(self, token: str, now: datetime | None = None):
        """(user, token row) for a live device token, else Unauthorized."""
        now = now or datetime.now(UTC)
        row = (
            self.repos.extension.token_by_hash(digest(token))
            if token.startswith(TOKEN_PREFIX)
            else None
        )
        if row is None or row.revoked_at is not None:
            raise Unauthorized("Invalid device token", code="invalid_token")
        user = self.repos.users.get(row.user_id)
        if user is None or user.status != "active":
            raise Unauthorized("Invalid device token", code="invalid_token")
        if row.last_used_at is None or as_utc(row.last_used_at) < now - timedelta(
            minutes=1
        ):
            row.last_used_at = now
            self.repos.session.commit()
        return user, row

    # --- clip ----------------------------------------------------------------
    def clip(self, user_id: uuid.UUID, body: ClipIn) -> tuple[JobAddOut, bool]:
        """A v1 job from text the extension read in the user's own browser.

        The URL is stored as a reference only; the server never fetches it.
        """
        from app.services.job import normalise_url  # avoids an import cycle at load

        url = normalise_url(body.url)
        text = normalise_text(body.text)
        head = [
            x for x in (body.title, body.company) if x and x.lower() not in text.lower()
        ]
        text = normalise_text("\n".join([*head, text]))
        if not text:
            raise Invalid("text must not be empty")
        digest_ = content_hash(text)
        dup = self.repos.jobs.find_duplicate(user_id, url, digest_)
        if dup is not None:
            return JobAddOut(job_id=dup.id, duplicate=True), False
        used = self.repos.jobs.count_created_since(
            user_id, datetime.now(UTC) - timedelta(hours=1)
        )
        if used >= settings.jobs_per_hour:
            raise TooManyRequests(
                "Too many jobs added; try again later",
                code="rate_limited",
                details={"limit": settings.jobs_per_hour, "window": "1h"},
            )
        job = self.repos.jobs.add(
            Job(
                user_id=user_id,
                source="text",
                url=url,
                raw_text=text,
                content_hash=digest_,
                source_channel="clipped",
                status=PROCESSING,
            )
        )
        log.info("job clipped user=%s job=%s hash=%s", user_id, job.id, digest_)
        self.queue.enqueue("extract_jd", user_id=str(user_id), job_id=job.id)
        return JobAddOut(job_id=job.id, status=PROCESSING), True
