"""Timezone conversion utilities: UTC ↔ Beijing (Asia/Shanghai)."""

from __future__ import annotations

from datetime import datetime, timezone, timedelta
from typing import Union

# Beijing timezone: UTC+8
BEIJING_TZ = timezone(timedelta(hours=8))


def timestamp_to_beijing(ts: Union[int, float]) -> datetime:
    """Convert a Unix timestamp to a Beijing-timezone datetime.

    Args:
        ts: Unix timestamp (seconds since epoch).

    Returns:
        Timezone-aware datetime in Asia/Shanghai (UTC+8).
    """
    dt_utc = datetime.fromtimestamp(ts, tz=timezone.utc)
    return dt_utc.astimezone(BEIJING_TZ)


def now_beijing() -> datetime:
    """Get the current time in Beijing timezone.

    Returns:
        Timezone-aware datetime in Asia/Shanghai (UTC+8).
    """
    return datetime.now(BEIJING_TZ)
