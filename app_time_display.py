"""Display-only timezone helpers. Never rewrite stored UTC timestamps."""
from __future__ import annotations
from datetime import datetime,timezone
from zoneinfo import ZoneInfo

def format_in_zone(timestamp, zone="UTC"):
    if not timestamp:return "Ikke registrert"
    try:
        dt=datetime.fromisoformat(str(timestamp).replace("Z","+00:00"))
        if dt.tzinfo is None:return str(timestamp)+" (tidssone ukjent)"
        return dt.astimezone(ZoneInfo(zone)).strftime("%d.%m.%Y %H:%M %Z")
    except (ValueError,KeyError):
        return str(timestamp)

def age_hours(timestamp, now=None):
    if not timestamp:return None
    try:
        observed=datetime.fromisoformat(str(timestamp).replace("Z","+00:00"))
        if observed.tzinfo is None:return None
        return max(0.,((now or datetime.now(timezone.utc))-observed).total_seconds()/3600)
    except (ValueError,TypeError):return None


def browser_timezone(st):
    """Use browser IANA zone, fall back to explicit UTC in headless contexts."""
    try:
        name=str(st.context.timezone or "UTC")
        ZoneInfo(name)
        return name
    except (AttributeError, KeyError, ValueError):
        return "UTC"

def local_display(st,timestamp):
    return format_in_zone(timestamp,browser_timezone(st))
