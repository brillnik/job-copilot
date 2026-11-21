import base64
import binascii

from app.core.exceptions import AppError


class InvalidCursor(AppError):
    status_code = 422
    code = "validation_error"
    detail = "Invalid cursor"


def encode(offset: int) -> str:
    return base64.urlsafe_b64encode(str(offset).encode()).decode()


def decode(cursor: str | None) -> int:
    if not cursor:
        return 0
    try:
        return max(0, int(base64.urlsafe_b64decode(cursor.encode()).decode()))
    except (ValueError, binascii.Error):
        raise InvalidCursor() from None
