"""Date-only visit scheduling policy for automatic dispatch."""

from __future__ import annotations

from datetime import date, datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError


# JobCreate currently stores a date, not a time. Until a time is supplied,
# treat the appointment as 09:00 in the owning organization's configured
# timezone (settings.timezone); UTC is the documented fallback.
DEFAULT_VISIT_TIME = time(hour=9)
DEFAULT_TIMEZONE = "UTC"
DISPATCH_LEAD_TIME = timedelta(hours=1)


def dispatch_due_at(visit_date: date, timezone_name: str | None, visit_time: time | None = None) -> datetime:
    try:
        zone = ZoneInfo(timezone_name or DEFAULT_TIMEZONE)
    except (ZoneInfoNotFoundError, ValueError):
        zone = ZoneInfo(DEFAULT_TIMEZONE)
    visit_at = datetime.combine(visit_date, visit_time or DEFAULT_VISIT_TIME, tzinfo=zone)
    return (visit_at - DISPATCH_LEAD_TIME).astimezone(timezone.utc)


def is_dispatch_due(visit_date: date, timezone_name: str | None, now: datetime, visit_time: time | None = None) -> bool:
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)
    return now.astimezone(timezone.utc) >= dispatch_due_at(visit_date, timezone_name, visit_time)
