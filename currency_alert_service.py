from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

try:
    import yfinance as yf
except Exception:
    yf = None

from settings_store import load_settings, save_settings
from notifier import send_pushover_alert

DEFAULT_ALERT = {
    "pair": "BRL/NOK",
    "symbol": "BRLNOK=X",
    "lower": 1.70,
    "upper": 2.20,
    "active": True,
    "pushover": True,
    "check_interval_minutes": 60,
    "cooldown_minutes": 720,
}
STATE_KEY = "currency_alert_runtime_v18675"


def _now() -> datetime:
    return datetime.now(timezone.utc).replace(microsecond=0)


def _parse(value: Any) -> datetime | None:
    try:
        dt = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)
    except Exception:
        return None


def _fetch(symbol: str) -> tuple[float | None, str]:
    if yf is None:
        return None, "yfinance er ikke tilgjengelig"
    try:
        hist = yf.Ticker(str(symbol).upper()).history(period="5d", interval="1d", auto_adjust=False, prepost=False)
        if hist is None or getattr(hist, "empty", True) or "Close" not in hist:
            return None, "fant ingen Close-data"
        close = hist["Close"].dropna()
        if close.empty:
            return None, "Close-data er tom"
        return float(close.iloc[-1]), ""
    except Exception as exc:
        return None, str(exc)[:240]


def _status(rate: float, lower: float, upper: float) -> str:
    if lower and rate <= lower:
        return "breach_lower"
    if upper and rate >= upper:
        return "breach_upper"
    return "normal"


def run_currency_alert_checks(force: bool = False) -> list[dict]:
    """Evaluate every saved currency alert and send Pushover on breach.

    A notification is sent on a new breach and repeated after cooldown while the
    breach remains active. Returning to normal resets the lifecycle.
    """
    settings = load_settings() or {}
    alerts = settings.get("currency_alerts_v1863af")
    if not isinstance(alerts, list) or not alerts:
        alerts = [dict(DEFAULT_ALERT)]
    root = settings.setdefault(STATE_KEY, {})
    now = _now()
    results: list[dict] = []

    for raw in alerts:
        alert = {**DEFAULT_ALERT, **(raw or {})}
        pair = str(alert.get("pair") or alert.get("symbol") or "Valuta")
        symbol = str(alert.get("symbol") or "").upper()
        key = f"{pair}:{symbol}"
        state = dict(root.get(key) or {})
        interval = max(1, int(alert.get("check_interval_minutes") or 60))
        cooldown = max(1, int(alert.get("cooldown_minutes") or int(alert.get("cooldown_hours") or 12) * 60))
        last_checked = _parse(state.get("last_checked_at"))
        if not force and last_checked and now - last_checked < timedelta(minutes=interval):
            results.append({"pair": pair, "symbol": symbol, "status": state.get("status", "skipped"), "sent": False, "skipped": True})
            continue
        if not bool(alert.get("active", True)):
            results.append({"pair": pair, "symbol": symbol, "status": "disabled", "sent": False})
            continue

        rate, error = _fetch(symbol)
        state["last_checked_at"] = now.isoformat()
        if rate is None:
            state.update({"last_error": error, "updated_at": now.isoformat()})
            root[key] = state
            results.append({"pair": pair, "symbol": symbol, "status": "error", "error": error, "sent": False})
            continue

        lower = float(alert.get("lower") or 0)
        upper = float(alert.get("upper") or 0)
        status = _status(rate, lower, upper)
        previous = str(state.get("status") or "normal")
        last_sent = _parse(state.get("last_sent_at"))
        repeat_due = bool(last_sent is None or now - last_sent >= timedelta(minutes=cooldown))
        should_send = status.startswith("breach") and (previous != status or repeat_due)
        sent = False
        send_error = ""
        if should_send and bool(alert.get("pushover", True)):
            relation = f"{rate:.4f} <= {lower:.4f}" if status == "breach_lower" else f"{rate:.4f} >= {upper:.4f}"
            message = f"{pair} har brutt grensen\nKurs: {rate:.4f}\nGrense: {relation}\nStatus: {status}"
            response = send_pushover_alert(message, title=f"Valutavarsel {pair}")
            if isinstance(response, tuple):
                sent = bool(response[0])
                send_error = str(response[1] if len(response) > 1 else "")
            else:
                sent = bool(response)
            if sent:
                state["last_sent_at"] = now.isoformat()
                state["last_sent_status"] = status
        if status == "normal" and previous != "normal":
            state["last_normal_at"] = now.isoformat()

        state.update({
            "pair": pair,
            "symbol": symbol,
            "rate": rate,
            "lower": lower,
            "upper": upper,
            "status": status,
            "previous_status": previous,
            "updated_at": now.isoformat(),
            "last_error": send_error,
        })
        root[key] = state
        settings.setdefault("currency_alert_latest_rates_v1864s", {})[symbol] = {
            "pair": pair, "symbol": symbol, "rate": rate, "updated_at": now.isoformat()
        }
        results.append({"pair": pair, "symbol": symbol, "rate": rate, "status": status, "sent": sent, "send_error": send_error})

    settings[STATE_KEY] = root
    save_settings(settings)
    return results
