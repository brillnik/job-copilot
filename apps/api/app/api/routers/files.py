import logging
from typing import Annotated

from fastapi import APIRouter, Depends, Response

from app.api.deps import get_storage
from app.core import signing
from app.core.exceptions import ErrorBody, NotFound
from app.services import crypto
from app.storage.base import Storage

log = logging.getLogger(__name__)
router = APIRouter(prefix="/files", tags=["files"])


@router.get(
    "/{token}",
    response_class=Response,
    responses={
        200: {"content": {"application/octet-stream": {}}, "description": "The file"},
        403: {"model": ErrorBody, "description": "Invalid or expired link"},
        404: {"model": ErrorBody, "description": "The file no longer exists"},
    },
)
def download(token: str, storage: Annotated[Storage, Depends(get_storage)]):
    """Serve a file for a signed link made by the API. The token is the credential."""
    claims = signing.verify(token)
    try:
        data = storage.read(claims["k"])
    except (FileNotFoundError, KeyError, OSError):
        raise NotFound("File not found") from None
    except Exception as e:
        if type(e).__name__ in ("NoSuchKey", "ClientError"):
            raise NotFound("File not found") from None
        raise
    if claims.get("dec"):
        data = crypto.decrypt(data)
    name = claims.get("fn") or "download"
    media = "application/pdf" if name.endswith(".pdf") else "application/zip"
    log.info("signed download served")
    return Response(
        data,
        media_type=media,
        headers={
            "Content-Disposition": f'attachment; filename="{name}"',
            "Cache-Control": "private, no-store",
        },
    )
