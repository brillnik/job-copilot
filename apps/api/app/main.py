import logging
import time
import uuid

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware

from app.api.router import api_router
from app.core.config import settings
from app.core.exceptions import register_exception_handlers
from app.core.logging import request_id_var, setup_logging

setup_logging()
log = logging.getLogger(__name__)

app = FastAPI(title="Job Copilot API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["X-Request-ID"],
)


@app.middleware("http")
async def request_log(request: Request, call_next):
    """Tag every request with an id and log one line per request with its duration."""
    rid = (request.headers.get("x-request-id") or "")[:64] or uuid.uuid4().hex[:12]
    token = request_id_var.set(rid)
    started = time.perf_counter()
    try:
        response = await call_next(request)
    except Exception:
        # Type only; the traceback is logged by the server's own error handler.
        log.error(
            "%s %s -> unhandled error after %.0fms",
            request.method,
            request.url.path,
            (time.perf_counter() - started) * 1000,
        )
        raise
    else:
        response.headers["X-Request-ID"] = rid
        # /health is polled constantly; keep it out of INFO.
        level = logging.DEBUG if request.url.path == "/health" else logging.INFO
        log.log(
            level,
            "%s %s -> %d in %.0fms",
            request.method,
            request.url.path,
            response.status_code,
            (time.perf_counter() - started) * 1000,
        )
        return response
    finally:
        request_id_var.reset(token)


register_exception_handlers(app)
app.include_router(api_router)
