"""Pure freshness checks used by scheduled health checks and tests."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone


def is_stale(observed_at: datetime | None, *, now: datetime, max_age: timedelta) -> bool:
    """Return true for absent, non-UTC, future, or overdue evidence."""

    if observed_at is None or observed_at.tzinfo is None or observed_at.utcoffset() != timezone.utc.utcoffset(observed_at):
        return True
    if now.tzinfo is None or now.utcoffset() != timezone.utc.utcoffset(now):
        raise ValueError("now must be an explicit UTC timestamp")
    return observed_at > now or now - observed_at > max_age
