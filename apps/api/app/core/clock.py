from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo

from app.core.config import settings


def as_utc(dt: datetime) -> datetime:
    """SQLite hands back naive datetimes; everything we store is UTC."""
    return dt.replace(tzinfo=UTC) if dt.tzinfo is None else dt.astimezone(UTC)


def local_day(now: datetime | None = None) -> str:
    now = as_utc(now) if now else datetime.now(UTC)
    return now.astimezone(ZoneInfo(settings.day_timezone)).date().isoformat()


def next_reset(now: datetime | None = None) -> datetime:
    """The next local midnight (when the daily run cap resets), in UTC."""
    tz = ZoneInfo(settings.day_timezone)
    local = (as_utc(now) if now else datetime.now(UTC)).astimezone(tz)
    midnight = (local + timedelta(days=1)).replace(
        hour=0, minute=0, second=0, microsecond=0
    )
    return midnight.astimezone(UTC)


def week_start(now: datetime | None = None) -> datetime:
    """Monday 00:00 in the configured timezone, in UTC."""
    tz = ZoneInfo(settings.day_timezone)
    local = (as_utc(now) if now else datetime.now(UTC)).astimezone(tz)
    monday = (local - timedelta(days=local.weekday())).replace(
        hour=0, minute=0, second=0, microsecond=0
    )
    return monday.astimezone(UTC)
