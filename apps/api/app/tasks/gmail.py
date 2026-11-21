"""Gmail tasks. Scheduling is a TODO (no scheduler exists yet): run `poll_all_gmail`
every 15 minutes, e.g. from cron via `python -m app.tasks.gmail`, as the fallback for
missed Pub/Sub pushes. Logs carry ids and counts only.
"""

import logging
import uuid
from collections.abc import Callable
from dataclasses import dataclass

from sqlalchemy.orm import Session

from app.ai.email_classifier import EmailClassifier
from app.repositories.manager import RepositoryManager
from app.services.gmail import SyncResult, process_new_messages
from app.services.google import GoogleClient
from app.tasks.queue import TaskQueue

log = logging.getLogger(__name__)


@dataclass
class GmailContext:
    session_factory: Callable[[], Session]
    google: GoogleClient
    classifier: EmailClassifier
    queue: TaskQueue | None = None


def poll_gmail(ctx: GmailContext, user_id: uuid.UUID | str) -> SyncResult:
    user_id = uuid.UUID(str(user_id))
    with ctx.session_factory() as session:
        return process_new_messages(
            RepositoryManager(session), ctx.google, ctx.classifier, user_id
        )


def poll_all_gmail(ctx: GmailContext) -> int:
    """Fan out one poll per connected user (enqueued if a queue is set, else inline)."""
    with ctx.session_factory() as session:
        ids = RepositoryManager(session).email.active_user_ids()
    for uid in ids:
        if ctx.queue is not None:
            ctx.queue.enqueue("poll_gmail", user_id=str(uid))
        else:
            poll_gmail(ctx, uid)
    log.info("poll_all_gmail users=%d", len(ids))
    return len(ids)


def main() -> None:  # python -m app.tasks.gmail
    from app.tasks.runtime import get_gmail_context

    poll_all_gmail(get_gmail_context())


if __name__ == "__main__":
    main()
