
from datetime import datetime, timedelta
import pytz

from settings_store import load_settings, save_settings


def _utc_now():
    return datetime.utcnow().replace(microsecond=0)


def _parse_iso(value):
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value).replace("Z", ""))
    except Exception:
        return None


def _oslo_end_of_day(days=0):
    now = datetime.now(pytz.timezone("Europe/Oslo"))
    target = now + timedelta(days=int(days))
    return target.replace(hour=23, minute=59, second=0, microsecond=0).astimezone(pytz.utc).replace(tzinfo=None)


def set_full_stop(enabled=True, until=None, reason="Ferie / full stopp"):
    settings = load_settings()
    settings["full_stop_enabled"] = bool(enabled)
    settings["full_stop_until"] = until
    settings["full_stop_reason"] = reason or "Ferie / full stopp"
    save_settings(settings)
    return settings


def set_full_stop_for_days(days, reason="Ferie / full stopp"):
    until = _oslo_end_of_day(days=days).isoformat()
    return set_full_stop(True, until=until, reason=reason)


def clear_full_stop():
    settings = load_settings()
    settings["full_stop_enabled"] = False
    settings["full_stop_until"] = None
    save_settings(settings)
    return settings


def full_stop_status():
    settings = load_settings()
    enabled = bool(settings.get("full_stop_enabled", False))
    until_raw = settings.get("full_stop_until")
    until = _parse_iso(until_raw)
    reason = settings.get("full_stop_reason", "Ferie / full stopp")

    if enabled and until and until <= _utc_now():
        settings["full_stop_enabled"] = False
        settings["full_stop_until"] = None
        save_settings(settings)
        enabled = False
        until_raw = None

    if not enabled:
        return {"active": False, "reason": "Full stopp er ikke aktiv", "until": None}

    if until_raw:
        return {
            "active": True,
            "reason": reason,
            "until": until_raw,
            "message": f"FULL STOPP aktiv til {until_raw} UTC – ingen søk, ingen auto-trading",
        }

    return {
        "active": True,
        "reason": reason,
        "until": None,
        "message": "FULL STOPP aktiv på ubestemt tid – ingen søk, ingen auto-trading",
    }


def search_allowed():
    status = full_stop_status()
    if status.get("active"):
        return False, status.get("message", "Full stopp aktiv")
    return True, "Søk tillatt"


def assert_search_allowed():
    allowed, reason = search_allowed()
    if not allowed:
        print(reason)
    return allowed
