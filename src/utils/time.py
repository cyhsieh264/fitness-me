"""Timezone-aware time utilities.

All timestamps in this project are stored as unix timestamps (Integer)
in the database. Use these functions for consistent time handling
regardless of server timezone.

- timestamp(): current unix timestamp (for DB storage)
- today_start_ts(): unix timestamp for the start of today
- now(): current datetime in configured timezone (for display/logic)
- today(): current date in configured timezone
- to_datetime(ts): convert unix timestamp to timezone-aware display
- days_ago_ts(n): unix timestamp for N days ago
"""

import time
from datetime import date, datetime
from zoneinfo import ZoneInfo

from src.config import settings


def _tz() -> ZoneInfo:
    return ZoneInfo(settings.timezone)


def timestamp() -> int:
    """Current unix timestamp (UTC epoch seconds) for DB storage."""
    return int(time.time())


def now() -> datetime:
    """Current datetime in configured timezone (for display/logic)."""
    return datetime.now(_tz()).replace(tzinfo=None)


def today() -> date:
    """Current date in configured timezone."""
    return datetime.now(_tz()).date()


def to_datetime(ts: int | None) -> datetime | None:
    """Convert unix timestamp to naive datetime in configured timezone."""
    if ts is None:
        return None
    return datetime.fromtimestamp(ts, tz=_tz()).replace(tzinfo=None)


def today_start_ts() -> int:
    """Unix timestamp for the start of today in configured timezone."""
    midnight = datetime.combine(today(), datetime.min.time(), tzinfo=_tz())
    return int(midnight.timestamp())


def days_ago_ts(days: int) -> int:
    """Unix timestamp for N days ago from now."""
    return timestamp() - (days * 86400)


def window_dates(
    days: int,
    date_from: date | None = None,
    date_to: date | None = None,
) -> tuple[date, date | None]:
    """Resolve a query window: explicit range wins over days-fallback.

    If either date_from or date_to is set, use them as-is (the other side
    stays None to mean unbounded). Otherwise fall back to "last `days` days
    inclusive" with no upper bound.
    """
    from datetime import timedelta

    if date_from is not None or date_to is not None:
        return (date_from or date.min, date_to)
    return (today() - timedelta(days=days), None)
