"""UTC arithmetic for recorded trades; unknown age never authorizes a signal exit."""
from datetime import datetime, timezone
from typing import Any


def utc_time(value: Any) -> datetime | None:
    try:
        stamp = value if isinstance(value, datetime) else datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        # Historical server timestamps were recorded without an offset in UTC.
        return (stamp.replace(tzinfo=timezone.utc) if stamp.tzinfo is None else stamp.astimezone(timezone.utc))
    except (ValueError, TypeError, OverflowError):
        return None


def elapsed_hours(value: Any, now: datetime | None = None) -> float | None:
    opened, reference = utc_time(value), utc_time(now or datetime.now(timezone.utc))
    if opened is None or reference is None or opened > reference:
        return None
    return (reference - opened).total_seconds() / 3600.0


def minimum_hold_met(position, minimum_hours: float, now: datetime | None = None) -> bool:
    age = elapsed_hours(position.get("last_added_at") or position.get("opened_at") or position.get("entry_date") or position.get("entry_time"), now)
    return float(minimum_hours) <= 0 or (age is not None and age >= float(minimum_hours))
