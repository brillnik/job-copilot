"""Autopilot by hand or from cron (no Celery Beat here).

    python -m app.apply.cli tick [--user <uuid>]    # save -> tailor -> approve -> queue apply
    python -m app.apply.cli digests                 # send due daily digests
    python -m app.apply.cli schedule                # prints the crontab lines

Cron (Asia/Kolkata): run `tick` every 15 minutes (it only acts for users whose Autopilot
is on and respects every cap), `digests` every 5 minutes (it sends once per user per day
after their digest_time), and the apply worker as a service:
    python -m app.apply.worker serve
"""

import argparse
import logging
import sys

from app.core.config import settings


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="autopilot")
    sub = ap.add_subparsers(dest="cmd", required=True)
    t = sub.add_parser("tick")
    t.add_argument("--user")
    sub.add_parser("digests")
    sub.add_parser("schedule")
    args = ap.parse_args(argv)
    if args.cmd == "schedule":
        tz = settings.day_timezone
        print(f"CRON_TZ={tz} */15 * * * * python -m app.apply.cli tick")
        print(f"CRON_TZ={tz} */5 * * * * python -m app.apply.cli digests")
        return 0
    logging.basicConfig(level=settings.log_level)
    from app.db.session import SessionLocal
    from app.repositories.manager import RepositoryManager
    from app.services import autopilot
    from app.tasks.runtime import get_context

    ctx = get_context()
    if args.cmd == "digests":
        print(autopilot.send_digests(ctx))
        return 0
    if args.user:
        print(autopilot.autopilot_tick(ctx, args.user))
    else:
        with SessionLocal() as session:
            ids = RepositoryManager(session).applications.autopilot_user_ids()
        print([autopilot.autopilot_tick(ctx, i) for i in ids])
    return 0


if __name__ == "__main__":
    sys.exit(main())
