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
