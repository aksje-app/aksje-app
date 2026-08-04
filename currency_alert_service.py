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
HEARTBEAT_KEY = "currency_alert_worker_v19220_rc5"
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


def _save_heartbeat(state: str, *, source: str, checked: int = 0, sent: int = 0, error: str = "") -> dict:
    now = _now().isoformat()
    state_name = str(state or "UNKNOWN").upper()
    source_name = str(source or "unknown")
    automatic_source = source_name in {"scheduled_cron", "web_background", "scanner_worker"}
    settings = load_settings() or {}
    previous = settings.get(HEARTBEAT_KEY) if isinstance(settings.get(HEARTBEAT_KEY), dict) else {}
    heartbeat = {
        **previous,
        "state": state_name,
        "source": source_name,
        "last_cycle_at": now,
        "last_success_at": now if state_name == "COMPLETED" else previous.get("last_success_at"),
        "checked": int(checked or 0),
        "sent": int(sent or 0),
        "last_error": str(error or "")[:500],
        "cycles": int(previous.get("cycles") or 0) + (1 if state_name in {"COMPLETED", "DEGRADED", "FAILED"} else 0),
    }
    if state_name == "RUNNING":
        heartbeat["started_at"] = now
        heartbeat["last_success_at"] = previous.get("last_success_at")
        heartbeat["cycles"] = int(previous.get("cycles") or 0)
    else:
        heartbeat["started_at"] = previous.get("started_at")
    if automatic_source and state_name != "RUNNING":
        heartbeat["last_automatic_at"] = now
        heartbeat["last_automatic_state"] = state_name
        heartbeat["last_automatic_error"] = str(error or "")[:500]
        if state_name == "COMPLETED":
            heartbeat["last_automatic_success_at"] = now
    settings[HEARTBEAT_KEY] = heartbeat
    save_settings(settings)
    return dict(heartbeat)


def get_currency_alert_health(max_age_minutes: int = 20) -> dict:
    """Return cross-process health from the durable cron/manual heartbeat.

    The Streamlit web process intentionally does not run an in-process FX
    thread on Render. Health must therefore come from persisted cron cycles,
    not process-local thread state.
    """
    settings = load_settings() or {}
    heartbeat = dict(settings.get(HEARTBEAT_KEY) or {})
    last_automatic = _parse(heartbeat.get("last_automatic_at"))
    age_seconds = None
    if last_automatic is not None:
        age_seconds = max(0, int((_now() - last_automatic).total_seconds()))
    state = str(heartbeat.get("last_automatic_state") or "NOT_STARTED").upper()
    healthy = bool(state == "COMPLETED" and age_seconds is not None and age_seconds <= max(1, int(max_age_minutes)) * 60)
    return {
        **heartbeat,
        "state": state,
        "healthy": healthy,
        "age_seconds": age_seconds,
        "max_age_minutes": max(1, int(max_age_minutes)),
        "mode": "durable_cron",
        "last_error": heartbeat.get("last_automatic_error") or "",
    }


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

    # yfinance history can fail transiently even when fast_info/download works.
    try:
        fast_info = getattr(ticker, "fast_info", None)
        last_price = None
        if fast_info is not None:
            try:
                last_price = fast_info.get("last_price") if hasattr(fast_info, "get") else fast_info["last_price"]
            except Exception:
                last_price = getattr(fast_info, "last_price", None)
        if last_price is not None and float(last_price) > 0:
            return float(last_price), "", _now().isoformat()
    except Exception as exc:
        errors.append(f"fast_info: {str(exc)[:160]}")

    try:
        downloaded = yf.download(
            str(symbol).upper(), period="5d", interval="1d", auto_adjust=False,
            progress=False, threads=False,
        )
        if downloaded is not None and not getattr(downloaded, "empty", True) and "Close" in downloaded:
            close = downloaded["Close"].dropna()
            if not close.empty:
                value = close.iloc[-1]
                if hasattr(value, "iloc"):
                    value = value.iloc[-1]
                quote_time = None
                try:
                    idx = close.index[-1]
                    quote_time = idx.isoformat() if hasattr(idx, "isoformat") else str(idx)
                except Exception:
                    quote_time = None
                return float(value), "", quote_time
    except Exception as exc:
        errors.append(f"download: {str(exc)[:160]}")
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
    notify: bool = True,
    source: str = "runtime",
) -> list[dict]:
    """Evaluate all saved FX alerts and persist a complete diagnostic trail.

    Currency checks must be callable independently of stock-market hours. A new
    breach is sent immediately; a continuing breach is repeated after cooldown.
    Returning to normal resets the lifecycle.
    """
    with _global_check_lock() as acquired:
        if not acquired:
            _event("scanner_skipped", reason="another_worker_holds_lock", source=source)
            return []
        _save_heartbeat("RUNNING", source=source)
        try:
            rows = _run_currency_alert_checks_locked(
                force=force, fetcher=fetcher, sender=sender, diagnostic_test=diagnostic_test,
                notify=notify, source=source,
            )
        except Exception as exc:
            _save_heartbeat("FAILED", source=source, error=str(exc))
            raise
        heartbeat_state = "DEGRADED" if any(row.get("status") == "error" for row in rows) else "COMPLETED"
        heartbeat_error = "; ".join(
            str(row.get("error") or row.get("send_error") or "")
            for row in rows if row.get("status") == "error" or row.get("send_error")
        )[:500]
        _save_heartbeat(
            heartbeat_state, source=source, checked=len(rows),
            sent=sum(1 for row in rows if row.get("sent")), error=heartbeat_error,
        )
        return rows


def _run_currency_alert_checks_locked(
    force: bool = False,
    *,
    fetcher: Callable[[str], tuple[float | None, str]] | None = None,
    sender: Callable[..., Any] | None = None,
    diagnostic_test: bool = False,
    notify: bool = True,
    source: str = "runtime",
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
    _event("scanner_started", run_id=run_id, force=bool(force), alerts=len(alerts), diagnostic_test=bool(diagnostic_test), notify=bool(notify), source=source)
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
        should_send = bool(notify) and status.startswith("breach") and (new_breach or repeat_due or diagnostic_test)
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
            notify=bool(notify),
            source=source,
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
            if not notify:
                reason = "notification_suppressed"
            else:
                reason = "cooldown_active" if last_sent is not None else "already_in_breach"
            _event("pushover_skipped", **base, rate=rate, status=status, reason=reason, source=source)

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
    _event("scanner_completed", run_id=run_id, checked=len(results), sent=sum(1 for r in results if r.get("sent")), source=source)
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
    original_runtime = settings.get(STATE_KEY)
    original_latest = settings.get("currency_alert_latest_rates_v1864s")
    original_heartbeat = settings.get(HEARTBEAT_KEY)
    try:
        settings["currency_alerts_v1863af"] = [selected]
        save_settings(settings)
        return run_currency_alert_checks(
            force=True, fetcher=forced_breach_fetcher, diagnostic_test=True,
            notify=True, source="diagnostic_test",
        )
    finally:
        restored = load_settings() or {}
        for key, original_value in (
            ("currency_alerts_v1863af", original),
            (STATE_KEY, original_runtime),
            ("currency_alert_latest_rates_v1864s", original_latest),
            (HEARTBEAT_KEY, original_heartbeat),
        ):
            if original_value is None:
                restored.pop(key, None)
            else:
                restored[key] = original_value
        save_settings(restored)
