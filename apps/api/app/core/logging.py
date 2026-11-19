"""Logging setup shared by the API process and the background task threads.

Convention (see app/tasks/jobs.py): log ids, counts, statuses and exception *types*.
Never log resume or job-posting text, tokens, or exception messages that may echo them.
"""

import logging
import logging.config
from contextvars import ContextVar

from app.core.config import settings

# Set per request by the middleware in app.main and copied onto task threads by the
# queue, so one id ties an API call to the background work it triggered.
request_id_var: ContextVar[str] = ContextVar("request_id", default="-")


class RequestIdFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        record.request_id = request_id_var.get()
        return True


def setup_logging() -> None:
    """Configure the root logger once; safe to call again (e.g. on reload)."""
    level = settings.log_level.upper()
    logging.config.dictConfig(
        {
            "version": 1,
            # uvicorn configures its own loggers before the app is imported.
            "disable_existing_loggers": False,
            "filters": {"request_id": {"()": RequestIdFilter}},
            "formatters": {
                "default": {
                    "format": (
                        "%(asctime)s %(levelname)-7s [%(request_id)s] "
                        "%(name)s: %(message)s"
                    ),
                    "datefmt": "%H:%M:%S",
                }
            },
            "handlers": {
                "console": {
                    "class": "logging.StreamHandler",
                    "formatter": "default",
                    "filters": ["request_id"],
                }
            },
            "root": {"level": "WARNING", "handlers": ["console"]},
            "loggers": {
                # Our code logs at LOG_LEVEL; third-party libraries stay quiet.
                "app": {"level": level},
                # Prints every SQL statement and its parameters, so opt-in only.
                "sqlalchemy.engine": {
                    "level": "INFO" if settings.log_sql else "WARNING"
                },
            },
        }
    )
