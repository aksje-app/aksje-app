
from datetime import datetime, timedelta, timezone
import pytz

from settings_store import load_settings, save_settings


def _utc_now():
    return datetime.now(timezone.utc).replace(microsecond=0)


def _parse_iso(value):
    """Parse ISO timestamps and always return timezone-aware UTC datetimes.

    Settings may contain old naive timestamps, new +00:00 timestamps, or Z-suffixed
    values. Normalizing here prevents TypeError when subtracting/comparing aware
    and naive datetimes.
    """
    if not value:
        return None
    try:
        text = str(value).strip()
        if not text:
            return None
        dt = datetime.fromisoformat(text.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc).replace(microsecond=0)
    except Exception:
        return None


def oslo_now():
    return datetime.now(pytz.timezone("Europe/Oslo"))


def pause_until(minutes=None, rest_of_day=False):
    """
    Sets pause_scanning_until in settings.
    """
    settings = load_settings()

    if rest_of_day:
        now = oslo_now()
        end = now.replace(hour=23, minute=59, second=0, microsecond=0)
        settings["pause_scanning_until"] = end.astimezone(pytz.utc).replace(tzinfo=None).isoformat()
    elif minutes:
        settings["pause_scanning_until"] = (_utc_now() + timedelta(minutes=int(minutes))).isoformat()
    else:
        settings["pause_scanning_until"] = None

    save_settings(settings)
    return settings["pause_scanning_until"]


def clear_pause():
    settings = load_settings()
    settings["pause_scanning_until"] = None
    save_settings(settings)


def should_run_background_scan(mark_complete=True):
    """
    Returns (allowed: bool, reason: str).
    The Render Cron may still wake up often, but this guard decides if it does real work.
    """
    settings = load_settings()

    if bool(settings.get("vacation_mode_enabled", False)):
        return False, f"Full stopp / ferie aktiv: {settings.get('full_stop_reason', '')}"

    if not bool(settings.get("background_scanning_enabled", True)):
        return False, "Bakgrunnssøk er deaktivert i app-innstillinger"

    pause_to = _parse_iso(settings.get("pause_scanning_until"))
    now = _utc_now()

    if pause_to and pause_to > now:
        return False, f"Bakgrunnssøk er pauset til {pause_to.isoformat()} UTC"

    try:
        interval = int(settings.get("scan_interval_minutes", 15))
    except Exception:
        interval = 15

    interval = max(1, min(interval, 1440))

    last_scan = _parse_iso(settings.get("last_scan_at"))
    if last_scan:
        elapsed = (now - last_scan).total_seconds() / 60.0
        if elapsed < interval:
            remaining = max(0, interval - elapsed)
            return False, f"Siste scan var for {elapsed:.1f} min siden. Neste om ca {remaining:.1f} min."

    return True, f"Scan tillatt. Intervall: {interval} min"


def mark_background_scan_started():
    settings = load_settings()
    settings["last_scan_at"] = _utc_now().isoformat()
    save_settings(settings)


def cron_status_text():
    settings = load_settings()
    allowed, reason = should_run_background_scan()
    pause_to = settings.get("pause_scanning_until")
    last_scan = settings.get("last_scan_at")
    scan_source = "legacy_settings"
    try:
        # The coordinated worker persists this independently of Streamlit and
        # is therefore the authoritative production heartbeat.
        from paper_scanner_runtime import load_scanner_status
        scanner_status = load_scanner_status()
        durable_scan = scanner_status.get("completed_at") or scanner_status.get("started_at")
        durable_dt = _parse_iso(durable_scan)
        legacy_dt = _parse_iso(last_scan)
        if durable_dt and (not legacy_dt or durable_dt > legacy_dt):
            last_scan = durable_dt.isoformat()
            scan_source = "paper_scanner_status"
    except Exception:
        pass
    interval = settings.get("scan_interval_minutes", 15)
    enabled = settings.get("background_scanning_enabled", True)
    last_scan_dt = _parse_iso(last_scan)
    scan_age_minutes = None
    scan_stale = False
    if last_scan_dt:
        scan_age_minutes = max(0.0, (_utc_now() - last_scan_dt).total_seconds() / 60.0)
        # Two expected intervals plus a small cron/startup allowance.
        stale_after = max(45, int(interval or 15) * 2 + 15)
        scan_stale = scan_age_minutes > stale_after

    return {
        "enabled": enabled,
        "vacation_mode": settings.get("vacation_mode_enabled", False),
        "full_stop_reason": settings.get("full_stop_reason", ""),
        "allowed": allowed,
        "reason": reason,
        "interval": interval,
        "pause_until": pause_to,
        "last_scan_at": last_scan,
        "last_scan_source": scan_source,
        "last_scan_age_minutes": scan_age_minutes,
        "scan_stale": scan_stale,
    }


def activate_full_stop(reason="Ferie / full stopp"):
    """
    Full stopp:
    - stopper bakgrunnssøk
    - stopper auto trading
    - setter ferie/full stopp flagg
    """
    settings = load_settings()
    settings["vacation_mode_enabled"] = True
    settings["background_scanning_enabled"] = False
    settings["auto_trading_enabled"] = False
    settings["full_stop_reason"] = reason
    save_settings(settings)
    return settings


def deactivate_full_stop():
    """
    Starter igjen:
    - bakgrunnssøk på
    - auto trading på
    - pause fjernet
    - last_scan_at nulles slik at neste Cron kan kjøre
    """
    settings = load_settings()
    settings["vacation_mode_enabled"] = False
    settings["background_scanning_enabled"] = True
    settings["auto_trading_enabled"] = True
    settings["pause_scanning_until"] = None
    settings["last_scan_at"] = None
    settings["full_stop_reason"] = ""
    save_settings(settings)
    return settings
