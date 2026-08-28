"""Timezone-aware datetime helpers.

Every timestamp in the platform is UTC and timezone-aware. Naive datetimes are
never persisted or compared.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta


def utc_now() -> datetime:
    """Current time as a timezone-aware UTC datetime."""
    return datetime.now(UTC)


def utc_in(*, minutes: int = 0, hours: int = 0, days: int = 0) -> datetime:
    """A UTC datetime offset from now."""
    return utc_now() + timedelta(minutes=minutes, hours=hours, days=days)


def ensure_utc(value: datetime | None) -> datetime | None:
    """Attach UTC to a naive datetime, or convert an aware one to UTC.

    PostgreSQL ``timestamptz`` values round-trip as aware datetimes, but values
    read from other sources (or SQLite in tests) may be naive.
    """
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def is_past(value: datetime | None) -> bool:
    """``True`` when the value is non-null and already elapsed."""
    normalised = ensure_utc(value)
    return normalised is not None and normalised <= utc_now()


def seconds_until(value: datetime) -> int:
    """Whole seconds remaining until ``value``; never negative."""
    delta = (ensure_utc(value) or utc_now()) - utc_now()
    return max(0, int(delta.total_seconds()))
