import base64
import hashlib

from cryptography.fernet import Fernet, InvalidToken

from app.core.config import settings


def _fernet() -> Fernet:
    key = settings.export_encryption_key.encode()
    if not key:  # dev only: derive from the signing secret
        key = base64.urlsafe_b64encode(
            hashlib.sha256(settings.signing_secret.encode()).digest()
        )
    return Fernet(key)


def encrypt(data: bytes) -> bytes:
    return _fernet().encrypt(data)


def decrypt(data: bytes) -> bytes:
    try:
        return _fernet().decrypt(data)
    except InvalidToken:
        raise ValueError("cannot decrypt") from None
