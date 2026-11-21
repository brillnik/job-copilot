"""Short-lived signed download links, checked by GET /files/{token}.

The token is a capability: it names one storage key and an expiry, and is bound to
the server's secret. Nothing personal is in it beyond the (opaque) storage key.
"""

import base64
import hashlib
import hmac
import json
import time

from app.core.config import settings
from app.core.exceptions import AppError


class InvalidLink(AppError):
    status_code = 403
    code = "invalid_link"
    detail = "This link is invalid or has expired"


def now() -> float:
    return time.time()  # indirection so tests can move the clock


def _b64(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode().rstrip("=")


def _unb64(text: str) -> bytes:
    return base64.urlsafe_b64decode(text + "=" * (-len(text) % 4))


def _mac(body: str) -> str:
    return _b64(
        hmac.new(
            settings.signing_secret.encode(), body.encode(), hashlib.sha256
        ).digest()
    )


def sign(key: str, ttl_s: int, *, filename: str, decrypt: bool = False) -> str:
    """A relative URL (or absolute with public_base_url) valid for `ttl_s` seconds."""
    body = _b64(
        json.dumps(
            {"k": key, "exp": int(now()) + ttl_s, "fn": filename, "dec": decrypt},
            separators=(",", ":"),
        ).encode()
    )
    return f"{settings.public_base_url.rstrip('/')}/files/{body}.{_mac(body)}"


def verify(token: str) -> dict:
    body, _, mac = token.partition(".")
    if not body or not hmac.compare_digest(mac, _mac(body)):
        raise InvalidLink()
    try:
        claims = json.loads(_unb64(body))
    except ValueError:
        raise InvalidLink() from None
    if claims.get("exp", 0) < now():
        raise InvalidLink()
    return claims
