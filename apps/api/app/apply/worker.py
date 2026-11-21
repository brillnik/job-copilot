"""Entrypoint of the apply worker (the separate `apply` queue / container).

    python -m app.apply.worker serve                       # poll for queued applications
    python -m app.apply.worker once                        # one polling pass, then exit
    python -m app.apply.worker run --user <uuid> --application <id>

With APPLY_WORKER_MODE=external (default) the API only queues rows and this process
claims them (queued -> running is an atomic compare-and-set, so several workers are
safe). With "inprocess" the API's own task queue runs `apply_application` instead.
Browser: the user's local Chrome (see app/apply/drivers.py). Egress limiting to the
target site plus our API is a deployment concern on top of the in-browser HostPolicy.
"""

import argparse
import logging
import sys
import time

from app.apply.runner import ApplyContext, run_application
from app.core.clock import local_day
from app.core.config import settings
from app.repositories.manager import RepositoryManager
from app.services.application import hour_key
from app.services.autopilot_prefs import daily_cap, site_cap

log = logging.getLogger(__name__)


def build_apply_context() -> ApplyContext:
    from app.apply.drivers import PlaywrightDriver
    from app.db.session import SessionLocal
    from app.tasks.runtime import build_embedder, build_storage

    return ApplyContext(
        session_factory=SessionLocal,
        storage=build_storage(),
        driver=PlaywrightDriver(),
        embedder=build_embedder(),
    )


def poll_once(ctx: ApplyContext, limit: int = 20) -> int:
    """Run queued playwright applications that currently have cap room."""
    from app.repositories.application import Caps

    if not settings.apply_enabled:
        return 0
    with ctx.session_factory() as session:
        repos = RepositoryManager(session)
        todo = []
        for app in repos.applications.queued("playwright", limit=limit):
            user = repos.users.get(app.user_id)
            caps = Caps(
                daily_cap(user), site_cap(app.site), settings.autopilot_ats_hourly_cap
            )
            if (
                repos.applications.has_room(
                    app.user_id, local_day(), hour_key(), app.site, app.ats, caps
                )
                is None
            ):
                todo.append((app.user_id, app.id))
    for user_id, app_id in todo:
        run_application(ctx, user_id, app_id)
    return len(todo)


def serve(ctx: ApplyContext, should_stop=lambda: False) -> None:
    while not should_stop():
        try:
            n = poll_once(ctx)
        except Exception as e:  # noqa: BLE001 - keep the worker alive
            log.error("apply poll failed error=%s", type(e).__name__)
            n = 0
        if n == 0:
            time.sleep(settings.apply_poll_s)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="apply-worker")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("serve")
    sub.add_parser("once")
    r = sub.add_parser("run")
    r.add_argument("--user", required=True)
    r.add_argument("--application", required=True)
    args = ap.parse_args(argv)
    logging.basicConfig(level=settings.log_level)
    ctx = build_apply_context()
    if args.cmd == "serve":
        serve(ctx)
    elif args.cmd == "once":
        print(poll_once(ctx))
    else:
        print(run_application(ctx, args.user, args.application))
    return 0


if __name__ == "__main__":
    sys.exit(main())
