"""Run discovery by hand or from cron (no Celery Beat here).

    python -m app.discovery.cli sync-lists
    python -m app.discovery.cli detect-ats
    python -m app.discovery.cli sync-source [--source himalayas | --company <id>]
    python -m app.discovery.cli sweep-closed
    python -m app.discovery.cli build-recommendations [--user <uuid>]
    python -m app.discovery.cli run-daily
    python -m app.discovery.cli schedule     # prints the crontab line

Schedule `run-daily` with DISCOVERY_SYNC_CRON in DISCOVERY_TIMEZONE (Asia/Kolkata).
"""

import argparse
import logging
import sys

from app.core.config import settings


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="discovery")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("sync-lists")
    sub.add_parser("detect-ats")
    sub.add_parser("sweep-closed")
    sub.add_parser("run-daily")
    sub.add_parser("schedule")
    s = sub.add_parser("sync-source")
    s.add_argument("--source", default="himalayas")
    s.add_argument("--company")
    r = sub.add_parser("build-recommendations")
    r.add_argument("--user")
    args = ap.parse_args(argv)

    if args.cmd == "schedule":
        print(
            f"CRON_TZ={settings.discovery_timezone} {settings.discovery_sync_cron} "
            "python -m app.discovery.cli run-daily"
        )
        return 0

    logging.basicConfig(level=settings.log_level)
    from app.db.session import SessionLocal
    from app.discovery import pipeline, tasks
    from app.tasks.runtime import get_context

    ctx = tasks.build_discovery_context(get_context())
    match args.cmd:
        case "sync-lists":
            print(tasks.sync_lists(ctx))
        case "detect-ats":
            print(pipeline.detect_stale(ctx))
        case "sync-source":
            print(
                tasks.sync_source(
                    ctx, args.company, None if args.company else args.source
                )
            )
        case "sweep-closed":
            print(tasks.sweep_closed(ctx))
        case "build-recommendations":
            if args.user:
                print(tasks.build_recommendations(ctx, args.user))
            else:
                with SessionLocal() as session:
                    ids = pipeline.active_user_ids(session)
                print(sum(tasks.build_recommendations(ctx, i) for i in ids))
        case "run-daily":
            print(tasks.sync_catalog(ctx))
    return 0


if __name__ == "__main__":
    sys.exit(main())
