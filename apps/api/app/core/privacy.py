"""One-way identifiers for the deletion audit. Never store the inputs."""

import hashlib
import hmac
import uuid

from app.core.config import settings


def hash_user_id(user_id: uuid.UUID) -> str:
    return hashlib.sha256(user_id.bytes).hexdigest()


def hash_sub(sub: str) -> str:
    """Keyed, so the audit table cannot be used to test guesses of a subject."""
    return hmac.new(
        settings.signing_secret.encode(), sub.encode(), hashlib.sha256
    ).hexdigest()
