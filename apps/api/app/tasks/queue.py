import logging
import time
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Protocol

from app.core.logging import request_id_var

log = logging.getLogger(__name__)


class TaskQueue(Protocol):
    """Background work. `enqueue("extract_jd", user_id=..., job_id=...)`.

    Implementations must pass user_id explicitly; tasks re-check ownership.
    The in-process queue below can be replaced by Celery without touching callers.
    """

    def enqueue(self, name: str, **kwargs: Any) -> None: ...


class InProcessQueue:
    def __init__(self, registry: Callable[[], dict[str, Callable[..., Any]]]) -> None:
        self._registry = registry
        self._pool = ThreadPoolExecutor(max_workers=4, thread_name_prefix="tasks")

    def enqueue(self, name: str, **kwargs: Any) -> None:
        # Pool threads do not inherit contextvars, so carry the request id across.
        rid = request_id_var.get()
        log.info("task %s enqueued args=%s", name, sorted(kwargs))
        self._pool.submit(self._run, name, kwargs, rid)

    def _run(self, name: str, kwargs: dict[str, Any], request_id: str) -> None:
        token = request_id_var.set(request_id)
        started = time.perf_counter()
        log.info("task %s started", name)
        try:
            self._registry()[name](**kwargs)
        except Exception as e:  # noqa: BLE001 - keep the worker thread alive
            # Type only: tracebacks and messages can echo resume or posting text.
            log.error(
                "task %s failed error=%s after %.1fs",
                name,
                type(e).__name__,
                time.perf_counter() - started,
            )
        else:
            log.info("task %s finished in %.1fs", name, time.perf_counter() - started)
        finally:
            request_id_var.reset(token)


class RecordingQueue:
    """Test double: records enqueued tasks instead of running them."""

    def __init__(self) -> None:
        self.calls: list[tuple[str, dict[str, Any]]] = []

    def enqueue(self, name: str, **kwargs: Any) -> None:
        self.calls.append((name, kwargs))

    def names(self) -> list[str]:
        return [n for n, _ in self.calls]
