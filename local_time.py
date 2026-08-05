"""Timezone helpers: UTC persistence with user-selected local presentation."""
from __future__ import annotations

import json
import os
from urllib.parse import quote
from datetime import datetime, timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError
from typing import Mapping

DEFAULT_TIMEZONE = os.getenv("APP_TIMEZONE", "Europe/Oslo")
AUTO_TIMEZONE = "AUTO"
SUPPORTED_TIMEZONES = [
    AUTO_TIMEZONE,
    "Europe/Oslo", "Europe/Lisbon", "Europe/Stockholm", "Europe/Helsinki",
    "Europe/Copenhagen", "America/New_York", "America/Sao_Paulo",
    "America/Fortaleza", "America/Manaus", "America/Cuiaba",
    "America/Rio_Branco", "America/Noronha", "UTC",
]
TIMEZONE_LABELS = {
    AUTO_TIMEZONE: "Automatisk - bruk nettleserens tidssone",
    "Europe/Oslo": "Norge - Europe/Oslo",
    "Europe/Lisbon": "Portugal - Europe/Lisbon",
    "America/Sao_Paulo": "Brasil - Sao Paulo / Brasilia",
    "America/Fortaleza": "Brasil - Fortaleza / Recife",
    "America/Manaus": "Brasil - Manaus",
    "America/Cuiaba": "Brasil - Cuiaba",
    "America/Rio_Branco": "Brasil - Rio Branco",
    "America/Noronha": "Brasil - Fernando de Noronha",
    "UTC": "UTC - teknisk tid",
}


def valid_timezone(value: object, default: str = DEFAULT_TIMEZONE) -> str:
    name = str(value or "").strip() or default
    if name == AUTO_TIMEZONE:
        return default
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


def _parse_datetime(value: datetime | str | None = None) -> datetime:
    if isinstance(value, datetime):
        return value
    if isinstance(value, str):
        text = value.strip()
        if not text:
            return datetime.now(timezone.utc)
        return datetime.fromisoformat(text.replace("Z", "+00:00"))
    return datetime.now(timezone.utc)


def as_local(value: datetime | str | None = None, timezone_name: str = DEFAULT_TIMEZONE) -> datetime:
    parsed = _parse_datetime(value)
    return as_utc(parsed).astimezone(ZoneInfo(valid_timezone(timezone_name)))


def local_iso(value: datetime | str | None = None, timezone_name: str = DEFAULT_TIMEZONE) -> str:
    return as_local(value, timezone_name).isoformat(timespec="seconds")


def local_display(value: datetime | str | None, timezone_name: str = DEFAULT_TIMEZONE) -> str:
    if not value:
        return "-"
    local = as_local(value, timezone_name)
    return f"{local:%d.%m.%Y %H:%M:%S} ({valid_timezone(timezone_name)})"


def local_compact_stamp(value: datetime | str | None = None, timezone_name: str = DEFAULT_TIMEZONE) -> str:
    return as_local(value, timezone_name).strftime("%Y%m%dT%H%M%S")


def local_run_id(prefix: str, value: datetime | str | None = None, timezone_name: str = DEFAULT_TIMEZONE) -> str:
    return f"{str(prefix or 'RUN').upper()}-{as_local(value, timezone_name):%Y%m%d-%H%M%S}"


def browser_timezone(streamlit_module: object, default: str = DEFAULT_TIMEZONE) -> str:
    """Return the browser IANA timezone captured by the tiny bootstrap below."""
    try:
        value = getattr(streamlit_module, "query_params").get("client_tz")
        return valid_timezone(value, default=default)
    except Exception:
        return valid_timezone(default)


def display_timezone_name(
    settings: Mapping[str, object] | None = None,
    *,
    streamlit_module: object | None = None,
    browser_tz: str | None = None,
    default: str = DEFAULT_TIMEZONE,
) -> str:
    """Resolve the user-facing timezone without changing scheduler timezones."""
    settings = settings or {}
    configured = str(settings.get("display_timezone") or AUTO_TIMEZONE).strip() or AUTO_TIMEZONE
    if configured != AUTO_TIMEZONE:
        return valid_timezone(configured, default=default)
    if browser_tz:
        return valid_timezone(browser_tz, default=default)
    if streamlit_module is not None:
        return browser_timezone(streamlit_module, default=default)
    return valid_timezone(default)


def display_time(
    value: datetime | str | None,
    timezone_name: str,
    *,
    include_seconds: bool = True,
    include_timezone: bool = True,
) -> str:
    if not value:
        return "-"
    local = as_local(value, timezone_name)
    time_format = "%d.%m.%Y %H:%M:%S" if include_seconds else "%d.%m.%Y %H:%M"
    result = local.strftime(time_format)
    return f"{result} ({valid_timezone(timezone_name)})" if include_timezone else result


def browser_clock_document(app_timezone_name: str = DEFAULT_TIMEZONE) -> str:
    """Return a self-contained live clock rendered by the user's browser.

    The PC clock uses ``new Date()`` and therefore follows the operating
    system/browser clock.  The app clock renders the same instant in the
    persisted presentation timezone.  This is display-only and never touches
    navigation, scheduler configuration or server-side timestamps.
    """
    app_timezone = valid_timezone(app_timezone_name)
    app_timezone_json = json.dumps(app_timezone)
    return f"""<!doctype html>
<html lang="nb">
<head>
<meta charset="utf-8">
<style>
  html, body {{ margin:0; padding:0; background:transparent; font-family:system-ui,-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif; }}
  .clock-card {{
    box-sizing:border-box; width:100%; padding:8px 10px; border:1px solid rgba(148,163,184,.28);
    border-radius:10px; background:rgba(15,23,42,.72); color:#f8fafc;
  }}
  .clock-row {{ display:grid; grid-template-columns:54px 1fr; column-gap:8px; align-items:baseline; }}
  .clock-row + .clock-row {{ margin-top:5px; }}
  .clock-label {{ color:#94a3b8; font-size:11px; font-weight:650; letter-spacing:.02em; }}
  .clock-time {{ font-variant-numeric:tabular-nums; font-size:13px; font-weight:700; white-space:nowrap; }}
  .clock-zone {{ margin-top:5px; color:#94a3b8; font-size:9.5px; line-height:1.25; overflow:hidden; text-overflow:ellipsis; white-space:nowrap; }}
</style>
</head>
<body>
<div class="clock-card" aria-label="PC-klokke og apptid">
  <div class="clock-row"><span class="clock-label">PC-tid</span><span id="pc-time" class="clock-time">--:--:--</span></div>
  <div class="clock-row"><span class="clock-label">App-tid</span><span id="app-time" class="clock-time">--:--:--</span></div>
  <div id="clock-zone" class="clock-zone"></div>
</div>
<script>
(() => {{
  const appTz = {app_timezone_json};
  const pcNode = document.getElementById('pc-time');
  const appNode = document.getElementById('app-time');
  const zoneNode = document.getElementById('clock-zone');
  const format = (date, timeZone) => new Intl.DateTimeFormat('nb-NO', {{
    timeZone, day:'2-digit', month:'2-digit', year:'numeric',
    hour:'2-digit', minute:'2-digit', second:'2-digit', hour12:false
  }}).format(date);
  const update = () => {{
    const now = new Date();
    let pcTz = 'lokal PC-tid';
    try {{ pcTz = Intl.DateTimeFormat().resolvedOptions().timeZone || pcTz; }} catch (_) {{}}
    try {{ pcNode.textContent = format(now, undefined); }} catch (_) {{ pcNode.textContent = now.toLocaleString('nb-NO'); }}
    try {{ appNode.textContent = format(now, appTz); }} catch (_) {{ appNode.textContent = pcNode.textContent; }}
    zoneNode.textContent = `PC: ${{pcTz}} · App: ${{appTz}}`;
  }};
  update();
  window.setInterval(update, 1000);
}})();
</script>
</body>
</html>"""


def install_browser_timezone_bootstrap() -> None:
    """Capture Intl timezone once without coupling scheduler execution to a browser."""
    try:
        import streamlit as st
        html = """
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
        """
        st.iframe("data:text/html;charset=utf-8," + quote(html), height=1, width=1)
    except Exception:
        pass
