import logging
from typing import Any

from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from starlette.exceptions import HTTPException as StarletteHTTPException

log = logging.getLogger(__name__)


class ErrorBody(BaseModel):
    """The one error shape every endpoint returns."""

    code: str
    message: str
    details: dict[str, Any] | list[Any] | None = None


class AppError(Exception):
    """Domain error raised by services; mapped to an HTTP response in one place."""

    status_code = status.HTTP_400_BAD_REQUEST
    code = "bad_request"
    detail = "Bad request"

    def __init__(
        self,
        detail: str | None = None,
        *,
        code: str | None = None,
        details: dict[str, Any] | None = None,
    ) -> None:
        self.detail = detail or self.detail
        self.code = code or self.code
        self.details = details
        super().__init__(self.detail)


class UnsupportedFileType(AppError):
    status_code = status.HTTP_415_UNSUPPORTED_MEDIA_TYPE
    code = "unsupported_file_type"
    detail = "Unsupported file type"


class FileTooLarge(AppError):
    status_code = status.HTTP_413_CONTENT_TOO_LARGE
    code = "file_too_large"
    detail = "File too large"


class EmptyFile(AppError):
    code = "empty_file"
    detail = "File is empty"


class NotFound(AppError):
    status_code = status.HTTP_404_NOT_FOUND
    code = "not_found"
    detail = "Not found"


class Conflict(AppError):
    status_code = status.HTTP_409_CONFLICT
    code = "conflict"
    detail = "Conflict"


class TooManyRequests(AppError):
    status_code = status.HTTP_429_TOO_MANY_REQUESTS
    code = "rate_limited"
    detail = "Too many requests"


class ExtractionFailed(AppError):
    status_code = status.HTTP_502_BAD_GATEWAY
    code = "extraction_failed"
    detail = "Could not extract a profile from the resume"


class ExtractionUnavailable(AppError):
    status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    code = "extraction_unavailable"
    detail = "Resume extraction is not configured"


def _body(code: str, message: str, details: Any = None) -> dict[str, Any]:
    return ErrorBody(code=code, message=message, details=details).model_dump()


def register_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(AppError)
    async def _handle(request: Request, exc: AppError) -> JSONResponse:
        # Domain errors are expected outcomes (4xx); only upstream failures are errors.
        log.log(
            logging.ERROR if exc.status_code >= 500 else logging.INFO,
            "%s %s -> %d %s (%s)",
            request.method,
            request.url.path,
            exc.status_code,
            exc.code,
            type(exc).__name__,
        )
        return JSONResponse(
            _body(exc.code, exc.detail, exc.details), status_code=exc.status_code
        )

    @app.exception_handler(RequestValidationError)
    async def _validation(
        request: Request, exc: RequestValidationError
    ) -> JSONResponse:
        errors = [
            {"loc": list(e["loc"]), "msg": e["msg"], "type": e["type"]}
            for e in exc.errors()
        ]
        # Field locations and error types only; the submitted values may be personal.
        log.info(
            "%s %s -> 422 validation failed: %s",
            request.method,
            request.url.path,
            "; ".join(f"{'.'.join(map(str, e['loc']))} ({e['type']})" for e in errors),
        )
        return JSONResponse(
            _body("validation_error", "Request validation failed", errors),
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
        )

    @app.exception_handler(StarletteHTTPException)
    async def _http(request: Request, exc: StarletteHTTPException) -> JSONResponse:
        log.log(
            logging.ERROR if exc.status_code >= 500 else logging.INFO,
            "%s %s -> %d %s",
            request.method,
            request.url.path,
            exc.status_code,
            exc.detail,
        )
        return JSONResponse(
            _body(f"http_{exc.status_code}", str(exc.detail)),
            status_code=exc.status_code,
            headers=getattr(exc, "headers", None),
        )
