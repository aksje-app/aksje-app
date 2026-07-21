"""Timezone helpers: UTC persistence with user-selected local presentation."""
from __future__ import annotations

import os
from datetime import datetime, timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

DEFAULT_TIMEZONE = os.getenv("APP_TIMEZONE", "Europe/Oslo")
SUPPORTED_TIMEZONES = [
    "Europe/Oslo", "Europe/Stockholm", "Europe/Helsinki",
    "Europe/Copenhagen", "America/New_York", "America/Sao_Paulo", "UTC",
]


def valid_timezone(value: object, default: str = DEFAULT_TIMEZONE) -> str:
    name = str(value or "").strip() or default
    try:
        ZoneInfo(name)
        return name
    except (ZoneInfoNotFoundError, ValueError):
        return default


def as_utc(value: datetime | None = None) -> datetime:
    current = value or datetime.now(timezone.utc)
    if current.tzinfo is None:
        current = current.replace(tzinfo=timezone.utc)
    return current.astimezone(timezone.utc)


def as_local(value: datetime | str | None = None, timezone_name: str = DEFAULT_TIMEZONE) -> datetime:
    if isinstance(value, str):
        value = datetime.fromisoformat(value.replace("Z", "+00:00"))
    return as_utc(value).astimezone(ZoneInfo(valid_timezone(timezone_name)))


def local_iso(value: datetime | str | None = None, timezone_name: str = DEFAULT_TIMEZONE) -> str:
    return as_local(value, timezone_name).isoformat(timespec="seconds")


def local_display(value: datetime | str | None, timezone_name: str = DEFAULT_TIMEZONE) -> str:
    if not value:
        return "-"
    local = as_local(value, timezone_name)
    return f"{local:%d.%m.%Y %H:%M:%S} ({valid_timezone(timezone_name)})"


def browser_timezone(streamlit_module: object) -> str:
    """Return the browser IANA timezone captured by the tiny bootstrap below."""
    try:
        value = getattr(streamlit_module, "query_params").get("client_tz")
        return valid_timezone(value)
    except Exception:
        return DEFAULT_TIMEZONE


def install_browser_timezone_bootstrap() -> None:
    """Capture Intl timezone once without coupling scheduler execution to a browser."""
    try:
        import streamlit.components.v1 as components
        components.html("""
        <script>
        (() => {
          try {
            const tz = Intl.DateTimeFormat().resolvedOptions().timeZone;
            const url = new URL(document.referrer);
            if (tz && url.searchParams.get('client_tz') !== tz) {
              url.searchParams.set('client_tz', tz);
              window.top.location.replace(url.toString());
            }
          } catch (_) {}
        })();
        </script>
        """, height=0, width=0)
    except Exception:
        pass
