from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
import os
import threading
from typing import Any, Callable

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
STATE_KEY = "currency_alert_runtime_v18678a"
LEGACY_STATE_KEY = "currency_alert_runtime_v18675"
EVENT_LOG_KEY = "alerts/currency_alert_events_v18678a.jsonl"
MAX_EVENT_ROWS = 250
_PROCESS_LOCK = threading.Lock()
_PG_ADVISORY_LOCK_ID = 1871301


@contextmanager
def _global_check_lock():
    """Serialize FX checks in one process and across Render web instances."""
    if not _PROCESS_LOCK.acquire(blocking=False):
        yield False
        return
    connection = None
    acquired = True
    try:
        database_url = os.getenv("DATABASE_URL", "").strip()
        if database_url:
            try:
                import psycopg2
                connection = psycopg2.connect(database_url, connect_timeout=5)
                cursor = connection.cursor()
                cursor.execute("SELECT pg_try_advisory_lock(%s)", (_PG_ADVISORY_LOCK_ID,))
                acquired = bool(cursor.fetchone()[0])
            except Exception as exc:
                # One process is still serialized locally. Record degraded
                # coordination, but do not disable alerts because DB had a
                # transient connection problem.
                _event("coordination_degraded", error=str(exc)[:240])
                acquired = True
        yield acquired
    finally:
        if connection is not None:
            try:
                if acquired:
                    cursor = connection.cursor()
                    cursor.execute("SELECT pg_advisory_unlock(%s)", (_PG_ADVISORY_LOCK_ID,))
                connection.close()
            except Exception:
                pass
        _PROCESS_LOCK.release()


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


def _storage():
    try:
        from services.storage_service import get_storage_service
        return get_storage_service()
    except Exception:
        return None


def _event(event: str, **data: Any) -> dict:
    row = {"timestamp": _now().isoformat(), "event": event, **data}
    storage = _storage()
    if storage is not None:
        try:
            storage.append_jsonl(EVENT_LOG_KEY, row)
        except Exception:
            pass
    return row


def get_currency_alert_events(limit: int = 100) -> list[dict]:
    storage = _storage()
    if storage is None:
        return []
    try:
        return list(storage.read_jsonl(EVENT_LOG_KEY, limit=max(1, min(int(limit), MAX_EVENT_ROWS))) or [])
    except Exception:
        return []


def get_currency_alert_runtime() -> dict:
    settings = load_settings() or {}
    root = settings.get(STATE_KEY)
    if not isinstance(root, dict):
        root = settings.get(LEGACY_STATE_KEY)
    return dict(root or {})


def _fetch(symbol: str) -> tuple[float | None, str, str | None]:
    """Fetch the freshest available FX quote.

    v18.7.13 used a daily candle, which could remain below/above a threshold
    even when the live intraday quote had crossed it. We now prefer 1-minute
    and 5-minute candles and only fall back to daily data.
    """
    if yf is None:
        return None, "yfinance er ikke tilgjengelig", None
    if not str(symbol or "").strip():
        return None, "mangler valutasymbol", None
    ticker = yf.Ticker(str(symbol).upper())
    attempts = (("1d", "1m"), ("5d", "5m"), ("5d", "1d"))
    errors: list[str] = []
    for period, interval in attempts:
        try:
            hist = ticker.history(period=period, interval=interval, auto_adjust=False, prepost=True)
            if hist is None or getattr(hist, "empty", True) or "Close" not in hist:
                errors.append(f"{interval}: ingen Close-data")
                continue
            close = hist["Close"].dropna()
            if close.empty:
                errors.append(f"{interval}: Close-data er tom")
                continue
            quote_time = None
            try:
                idx = close.index[-1]
                quote_time = idx.isoformat() if hasattr(idx, "isoformat") else str(idx)
            except Exception:
                quote_time = None
            return float(close.iloc[-1]), "", quote_time
        except Exception as exc:
            errors.append(f"{interval}: {str(exc)[:160]}")
    return None, "; ".join(errors)[:500] or "fant ingen valutadata", None


def _normalize_fetch_response(response: Any) -> tuple[float | None, str, str | None]:
    if isinstance(response, tuple):
        rate = response[0] if len(response) > 0 else None
        error = response[1] if len(response) > 1 else ""
        quote_time = response[2] if len(response) > 2 else None
        return rate, str(error or ""), str(quote_time) if quote_time else None
    return response, "", None


def _status(rate: float, lower: float, upper: float) -> str:
    if lower and rate <= lower:
        return "breach_lower"
    if upper and rate >= upper:
        return "breach_upper"
    return "normal"


def _normalize_send_response(response: Any) -> tuple[bool, str]:
    if isinstance(response, tuple):
        return bool(response[0]), str(response[1] if len(response) > 1 and response[1] else "")
    return bool(response), ""


def run_currency_alert_checks(
    force: bool = False,
    *,
    fetcher: Callable[[str], tuple[float | None, str]] | None = None,
    sender: Callable[..., Any] | None = None,
    diagnostic_test: bool = False,
) -> list[dict]:
    """Evaluate all saved FX alerts and persist a complete diagnostic trail.

    Currency checks must be callable independently of stock-market hours. A new
    breach is sent immediately; a continuing breach is repeated after cooldown.
    Returning to normal resets the lifecycle.
    """
    with _global_check_lock() as acquired:
        if not acquired:
            _event("scanner_skipped", reason="another_worker_holds_lock")
            return []
        return _run_currency_alert_checks_locked(
            force=force, fetcher=fetcher, sender=sender, diagnostic_test=diagnostic_test
        )


def _run_currency_alert_checks_locked(
    force: bool = False,
    *,
    fetcher: Callable[[str], tuple[float | None, str]] | None = None,
    sender: Callable[..., Any] | None = None,
    diagnostic_test: bool = False,
) -> list[dict]:
    fetcher = fetcher or _fetch
    sender = sender or send_pushover_alert
    settings = load_settings() or {}
    alerts = settings.get("currency_alerts_v1863af")
    if not isinstance(alerts, list) or not alerts:
        alerts = [dict(DEFAULT_ALERT)]

    root = settings.setdefault(STATE_KEY, {})
    if not root and isinstance(settings.get(LEGACY_STATE_KEY), dict):
        root.update(settings.get(LEGACY_STATE_KEY) or {})

    now = _now()
    run_id = now.strftime("%Y%m%dT%H%M%SZ")
    _event("scanner_started", run_id=run_id, force=bool(force), alerts=len(alerts), diagnostic_test=bool(diagnostic_test))
    results: list[dict] = []

    for raw in alerts:
        alert = {**DEFAULT_ALERT, **(raw or {})}
        pair = str(alert.get("pair") or alert.get("symbol") or "Valuta")
        symbol = str(alert.get("symbol") or "").upper().strip()
        key = f"{pair}:{symbol}"
        state = dict(root.get(key) or {})
        interval = max(1, int(alert.get("check_interval_minutes") or 60))
        cooldown = max(1, int(alert.get("cooldown_minutes") or int(alert.get("cooldown_hours") or 12) * 60))
        last_checked = _parse(state.get("last_checked_at"))

        base = {
            "run_id": run_id,
            "pair": pair,
            "symbol": symbol,
            "lower": float(alert.get("lower") or 0),
            "upper": float(alert.get("upper") or 0),
            "check_interval_minutes": interval,
            "cooldown_minutes": cooldown,
        }

        # A threshold/configuration change starts a new lifecycle and must be
        # evaluated immediately instead of inheriting an obsolete breach.
        config_signature = f"{symbol}|{base['lower']:.8f}|{base['upper']:.8f}|{int(bool(alert.get('active', True)))}"
        config_changed = state.get("config_signature") != config_signature
        if config_changed:
            state.pop("last_sent_at", None)
            state.pop("last_sent_status", None)
            state["status"] = "normal"
            state["previous_status"] = "normal"
            state["config_signature"] = config_signature
            last_checked = None
            _event("alert_configuration_changed", **base)

        if not bool(alert.get("active", True)):
            state.update({"status": "disabled", "updated_at": now.isoformat()})
            root[key] = state
            result = {**base, "status": "disabled", "sent": False, "reason": "alert_disabled"}
            results.append(result)
            _event("alert_skipped", **result)
            continue

        if not force and last_checked and now - last_checked < timedelta(minutes=interval):
            next_check = last_checked + timedelta(minutes=interval)
            result = {
                **base,
                "status": state.get("status", "skipped"),
                "sent": False,
                "skipped": True,
                "reason": "check_interval_active",
                "last_checked_at": last_checked.isoformat(),
                "next_check_at": next_check.isoformat(),
                "next_alert_allowed_at": state.get("next_alert_allowed_at"),
            }
            results.append(result)
            _event("alert_skipped", **result)
            continue

        _event("rate_fetch_started", **base)
        rate, fetch_error, quote_time = _normalize_fetch_response(fetcher(symbol))
        state["last_checked_at"] = now.isoformat()
        state["last_run_id"] = run_id
        if rate is None:
            state.update({"last_error": fetch_error, "updated_at": now.isoformat(), "status": "error"})
            root[key] = state
            result = {**base, "status": "error", "error": fetch_error, "sent": False, "reason": "rate_fetch_failed"}
            results.append(result)
            _event("rate_fetch_failed", **result)
            continue

        rate = float(rate)
        lower = base["lower"]
        upper = base["upper"]
        status = _status(rate, lower, upper)
        previous = str(state.get("status") or "normal")
        previous_rate_raw = state.get("last_rate", state.get("rate"))
        try:
            previous_rate = float(previous_rate_raw) if previous_rate_raw is not None else None
        except Exception:
            previous_rate = None
        crossed_lower = bool(previous_rate is not None and lower and previous_rate > lower and rate <= lower)
        crossed_upper = bool(previous_rate is not None and upper and previous_rate < upper and rate >= upper)
        crossed_threshold = crossed_lower or crossed_upper
        last_sent = _parse(state.get("last_sent_at"))
        repeat_due = bool(last_sent is None or now - last_sent >= timedelta(minutes=cooldown))
        new_breach = status.startswith("breach") and (previous != status or crossed_threshold)
        should_send = status.startswith("breach") and (new_breach or repeat_due or diagnostic_test)
        pushover_requested = bool(alert.get("pushover", True))
        sent = False
        send_error = ""
        reason = "normal"

        _event(
            "rate_evaluated",
            **base,
            rate=rate,
            status=status,
            previous_status=previous,
            previous_rate=previous_rate,
            crossed_threshold=crossed_threshold,
            new_breach=new_breach,
            repeat_due=repeat_due,
            should_send=should_send,
            pushover_requested=pushover_requested,
        )

        if should_send and pushover_requested:
            relation = f"{rate:.4f} <= {lower:.4f}" if status == "breach_lower" else f"{rate:.4f} >= {upper:.4f}"
            prefix = "DIAGNOSETEST - " if diagnostic_test else ""
            message = f"{prefix}{pair} har brutt grensen\nKurs: {rate:.4f}\nGrense: {relation}\nStatus: {status}"
            _event("pushover_send_started", **base, rate=rate, status=status, diagnostic_test=bool(diagnostic_test))
            try:
                response = sender(message, title=f"Valutavarsel {pair}")
                sent, send_error = _normalize_send_response(response)
            except Exception as exc:
                sent, send_error = False, str(exc)[:240]
            if sent:
                state["last_sent_at"] = now.isoformat()
                state["last_sent_status"] = status
                state["last_send_ok"] = True
                reason = "pushover_sent"
                _event("pushover_sent", **base, rate=rate, status=status)
            else:
                state["last_send_ok"] = False
                reason = "pushover_failed"
                _event("pushover_failed", **base, rate=rate, status=status, error=send_error)
        elif should_send and not pushover_requested:
            reason = "pushover_disabled_for_alert"
            _event("pushover_skipped", **base, rate=rate, status=status, reason=reason)
        elif status.startswith("breach"):
            reason = "cooldown_active" if last_sent is not None else "already_in_breach"
            _event("pushover_skipped", **base, rate=rate, status=status, reason=reason)

        if status == "normal" and previous != "normal":
            state["last_normal_at"] = now.isoformat()
            reason = "lifecycle_reset"
            _event("alert_normalized", **base, rate=rate, previous_status=previous)

        next_check = now + timedelta(minutes=interval)
        next_alert_allowed = (last_sent + timedelta(minutes=cooldown)) if last_sent else None
        if sent:
            next_alert_allowed = now + timedelta(minutes=cooldown)
        state.update({
            "pair": pair,
            "symbol": symbol,
            "rate": rate,
            "last_rate": rate,
            "quote_time": quote_time,
            "lower": lower,
            "upper": upper,
            "status": status,
            "previous_status": previous,
            "updated_at": now.isoformat(),
            "next_check_at": next_check.isoformat(),
            "next_alert_allowed_at": next_alert_allowed.isoformat() if next_alert_allowed else None,
            "last_error": send_error or fetch_error,
            "last_reason": reason,
            "config_signature": config_signature,
        })
        root[key] = state
        settings.setdefault("currency_alert_latest_rates_v1864s", {})[symbol] = {
            "pair": pair, "symbol": symbol, "rate": rate,
            "updated_at": now.isoformat(), "quote_time": quote_time,
        }
        results.append({
            **base,
            "rate": rate,
            "last_rate": rate,
            "quote_time": quote_time,
            "status": status,
            "previous_status": previous,
            "previous_rate": previous_rate,
            "crossed_threshold": crossed_threshold,
            "quote_time": quote_time,
            "trigger": status.startswith("breach"),
            "should_send": should_send,
            "sent": sent,
            "send_error": send_error,
            "reason": reason,
            "last_checked_at": now.isoformat(),
            "next_check_at": next_check.isoformat(),
            "next_alert_allowed_at": next_alert_allowed.isoformat() if next_alert_allowed else None,
        })

    settings[STATE_KEY] = root
    save_settings(settings)
    _event("scanner_completed", run_id=run_id, checked=len(results), sent=sum(1 for r in results if r.get("sent")))
    return results


def run_currency_alert_diagnostic_test(symbol: str | None = None) -> list[dict]:
    """Exercise fetch -> trigger -> alert engine -> Pushover without changing thresholds permanently."""
    settings = load_settings() or {}
    alerts = settings.get("currency_alerts_v1863af")
    if not isinstance(alerts, list) or not alerts:
        alerts = [dict(DEFAULT_ALERT)]
    selected = None
    wanted = str(symbol or "").upper().strip()
    for row in alerts:
        if not wanted or str((row or {}).get("symbol") or "").upper() == wanted:
            selected = {**DEFAULT_ALERT, **(row or {})}
            break
    selected = selected or {**DEFAULT_ALERT, **(alerts[0] or {})}

    def forced_breach_fetcher(_symbol: str) -> tuple[float | None, str]:
        real_rate, error = _fetch(_symbol)
        if real_rate is None:
            return None, error, None
        lower = float(selected.get("lower") or 0)
        upper = float(selected.get("upper") or 0)
        if upper:
            return max(float(real_rate), upper + max(abs(upper) * 0.001, 0.0001)), "", _now().isoformat()
        return min(float(real_rate), lower - max(abs(lower) * 0.001, 0.0001)), "", _now().isoformat()

    original = settings.get("currency_alerts_v1863af")
    try:
        settings["currency_alerts_v1863af"] = [selected]
        save_settings(settings)
        return run_currency_alert_checks(force=True, fetcher=forced_breach_fetcher, diagnostic_test=True)
    finally:
        restored = load_settings() or {}
        if original is None:
            restored.pop("currency_alerts_v1863af", None)
        else:
            restored["currency_alerts_v1863af"] = original
        save_settings(restored)
