import logging
from settings_store import load_settings

import os
import requests
import hashlib
import threading
from datetime import datetime, timezone
from storage_architecture import runtime_data_path, runtime_log_path
from durable_runtime import append_event, read_events, read_json, write_json
from runtime_safety import notifications_allowed

try:
    from runtime_env import load_app_env

    load_app_env()
except Exception:
    pass

PUSHOVER_APP_TOKEN = os.getenv("PUSHOVER_APP_TOKEN")
PUSHOVER_USER_KEY = os.getenv("PUSHOVER_USER_KEY")
PUSHOVER_AUDIT_PATH = runtime_log_path("pushover_audit.jsonl")
PUSHOVER_DEDUPE_KEY = "notifications/pushover_dedupe.json"
PUSHOVER_DEDUPE_PATH = runtime_data_path("notifications", "pushover_dedupe.json")
PUSHOVER_MESSAGE_LIMIT = 1024
PUSHOVER_TITLE_LIMIT = 250
TRADE_NOTIFICATION_KEY = "notifications/paper_trade_receipts.json"
TRADE_NOTIFICATION_PATH = runtime_data_path("notifications", "paper_trade_receipts.json")
_TRADE_NOTIFICATION_LOCK = threading.RLock()
_TRADE_NOTIFICATION_MAX_ATTEMPTS = 5


def _trim_text(value, limit):
    text = str(value or "")
    return text if len(text) <= int(limit) else text[:max(0, int(limit) - 1)].rstrip() + "…"


def _runtime_release_label() -> str:
    try:
        from runtime_identity import current_runtime_identity
        identity = current_runtime_identity("notifier")
        return f"{identity.get('version')} · commit {identity.get('commit_short')}"
    except Exception:
        from app_version import APP_VERSION
        return APP_VERSION


def fit_pushover_message(message, *, required_tail="", limit=PUSHOVER_MESSAGE_LIMIT):
    """Shorten only between complete lines and include a required footer once."""
    text = str(message or "").replace("\r\n", "\n").replace("\r", "\n").strip()
    tail = str(required_tail or "").strip()
    if tail and text.endswith(tail):
        text = text[:-len(tail)].rstrip()
    lines = []
    for line in text.splitlines():
        if not lines or line != lines[-1]:
            lines.append(line)
    suffix = ("\n" + tail) if tail else ""
    if len("\n".join(lines) + suffix) <= int(limit):
        return "\n".join(lines) + suffix
    kept = []
    marker = "… flere detaljer i rapportlenken"
    budget = int(limit) - len(suffix) - len(marker) - 2
    for line in lines:
        candidate = "\n".join(kept + [line])
        if len(candidate) > budget:
            break
        kept.append(line)
    return ("\n".join(kept) + "\n" + marker + suffix).strip()


def _notification_fingerprint(title, message, url) -> str:
    raw = "\n".join((str(title or ""), str(message or ""), str(url or "")))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _recent_duplicate(title, message, url, *, now=None) -> bool:
    now = now or datetime.now(timezone.utc)
    window = max(30, int(os.getenv("PUSHOVER_DEDUPE_SECONDS", "600") or 600))
    fingerprint = _notification_fingerprint(title, message, url)
    ledger = read_json(PUSHOVER_DEDUPE_KEY, PUSHOVER_DEDUPE_PATH, {})
    raw = str((ledger if isinstance(ledger, dict) else {}).get(fingerprint) or "")
    try:
        sent_at = datetime.fromisoformat(raw.replace("Z", "+00:00")).astimezone(timezone.utc)
        return (now - sent_at).total_seconds() < window
    except Exception:
        return False


def _record_notification_fingerprint(title, message, url, *, now=None) -> None:
    now = now or datetime.now(timezone.utc)
    fingerprint = _notification_fingerprint(title, message, url)
    ledger = read_json(PUSHOVER_DEDUPE_KEY, PUSHOVER_DEDUPE_PATH, {})
    ledger = dict(ledger) if isinstance(ledger, dict) else {}
    cutoff = now.timestamp() - 86400
    clean = {}
    for key, raw in ledger.items():
        try:
            when = datetime.fromisoformat(str(raw).replace("Z", "+00:00")).astimezone(timezone.utc)
            if when.timestamp() >= cutoff:
                clean[str(key)] = when.isoformat()
        except Exception:
            continue
    clean[fingerprint] = now.isoformat()
    write_json(PUSHOVER_DEDUPE_KEY, PUSHOVER_DEDUPE_PATH, clean)


def _log_delivery(title, success, detail, *, has_url=False):
    append_event("notifications/pushover_audit.jsonl", PUSHOVER_AUDIT_PATH, {
        "at": datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds"),
        "channel": "PUSHOVER", "title": str(title), "success": bool(success),
        "detail": str(detail or "OK")[:500], "has_url": bool(has_url),
    })


def pushover_audit(limit=500):
    return read_events("notifications/pushover_audit.jsonl", PUSHOVER_AUDIT_PATH, limit=int(limit))


def _trade_receipt_store() -> dict:
    value = read_json(TRADE_NOTIFICATION_KEY, TRADE_NOTIFICATION_PATH, {})
    return dict(value) if isinstance(value, dict) else {}


def trade_notification_receipts(limit=100) -> list[dict]:
    """Return newest durable Paper BUY/SELL delivery receipts."""
    rows = [dict(row) for row in _trade_receipt_store().values() if isinstance(row, dict)]
    rows.sort(key=lambda row: str(row.get("updated_at") or row.get("created_at") or ""), reverse=True)
    return rows[:max(1, int(limit or 100))]


def trade_notification_health() -> dict:
    rows = trade_notification_receipts(limit=500)
    unresolved = [row for row in rows if str(row.get("status") or "") in {"PENDING", "FAILED", "DISABLED"}]
    return {
        "status": "DEGRADED" if unresolved else "OK",
        "total": len(rows),
        "unresolved": len(unresolved),
        "failed": sum(1 for row in unresolved if row.get("status") == "FAILED"),
        "disabled": sum(1 for row in unresolved if row.get("status") == "DISABLED"),
        "latest_unresolved": unresolved[:10],
    }


def _delivery_status(ok: bool, detail: str) -> str:
    text = str(detail or "").lower()
    if ok and "duplicate" in text:
        return "DUPLICATE"
    if ok:
        return "SENT"
    if "disabled" in text or "deaktiv" in text:
        return "DISABLED"
    return "FAILED"


def _attempt_trade_notification(trade_id: str, payload: dict) -> tuple[bool, str]:
    response = notify_trade(**payload)
    ok, detail = normalize_notification_result(response)
    with _TRADE_NOTIFICATION_LOCK:
        store = _trade_receipt_store()
        current = dict(store.get(trade_id) or {})
        current.update({
            "trade_id": trade_id,
            "status": _delivery_status(ok, detail),
            "attempts": int(current.get("attempts") or 0) + 1,
            "last_attempt_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "updated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "detail": str(detail or "HTTP 200"),
        })
        store[trade_id] = current
        write_json(TRADE_NOTIFICATION_KEY, TRADE_NOTIFICATION_PATH, store)
    return ok, detail


def queue_trade_notification(trade_id: str, **payload) -> tuple[bool, str]:
    """Persist a trade notification before delivery; retry never repeats the trade."""
    trade_id = str(trade_id or "").strip()
    if not trade_id:
        return False, "missing trade_id"
    safe_payload = dict(payload)
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    with _TRADE_NOTIFICATION_LOCK:
        store = _trade_receipt_store()
        existing = dict(store.get(trade_id) or {})
        if existing.get("status") in {"SENT", "DUPLICATE"}:
            return True, str(existing.get("detail") or "already delivered")
        store[trade_id] = {
            **existing,
            "trade_id": trade_id,
            "trade_type": str(safe_payload.get("trade_type") or "").upper(),
            "ticker": str(safe_payload.get("ticker") or "").upper(),
            "status": "PENDING",
            "attempts": int(existing.get("attempts") or 0),
            "created_at": existing.get("created_at") or now,
            "updated_at": now,
            "payload": safe_payload,
        }
        write_json(TRADE_NOTIFICATION_KEY, TRADE_NOTIFICATION_PATH, store)
    return _attempt_trade_notification(trade_id, safe_payload)


def retry_pending_trade_notifications(limit=10) -> dict:
    """Retry delivery only. It never invokes or repeats BUY/SELL execution."""
    rows = trade_notification_receipts(limit=500)
    candidates = [
        row for row in reversed(rows)
        if str(row.get("status") or "") in {"PENDING", "FAILED", "DISABLED"}
        and int(row.get("attempts") or 0) < _TRADE_NOTIFICATION_MAX_ATTEMPTS
        and isinstance(row.get("payload"), dict)
    ][:max(1, int(limit or 10))]
    sent = failed = 0
    for row in candidates:
        ok, _detail = _attempt_trade_notification(str(row.get("trade_id") or ""), dict(row.get("payload") or {}))
        sent += int(bool(ok))
        failed += int(not ok)
    health = trade_notification_health()
    return {"state": "COMPLETED", "attempted": len(candidates), "sent": sent, "failed": failed, **health}


def pushover_enabled():
    allowed, _reason = notifications_allowed()
    return bool(allowed)


def validate_pushover_credentials():
    """Validate configured credentials without sending a notification."""
    if not PUSHOVER_APP_TOKEN or not PUSHOVER_USER_KEY:
        return {"ok": False, "status_code": None,
                "response_text": "Mangler PUSHOVER_APP_TOKEN eller PUSHOVER_USER_KEY"}
    try:
        response = requests.post(
            "https://api.pushover.net/1/users/validate.json",
            data={"token": PUSHOVER_APP_TOKEN, "user": PUSHOVER_USER_KEY}, timeout=10,
        )
        return {"ok": response.status_code == 200, "status_code": response.status_code,
                "response_text": str(response.text or "")[:1200]}
    except Exception as exc:
        return {"ok": False, "status_code": None, "response_text": str(exc)[:1200]}


def normalize_notification_result(response):
    """Return one canonical ``(ok, detail)`` pair for legacy/new notifier shapes."""
    if isinstance(response, tuple):
        ok = bool(response[0]) if response else False
        detail = response[1] if len(response) > 1 else ""
        return ok, str(detail or "")
    return bool(response), ""


def send_pushover_alert(message, title="AI Aksje Analyzer", url=None, url_title=None, *, priority=0):
    title = _trim_text(title, PUSHOVER_TITLE_LIMIT)
    message = fit_pushover_message(message)
    url_title = _trim_text(url_title, PUSHOVER_TITLE_LIMIT) if url_title else None
    allowed, safety_reason = notifications_allowed()
    if not allowed:
        print(f"Pushover blokkert: {safety_reason}")
        _log_delivery(title, False, safety_reason, has_url=bool(url))
        return False, safety_reason
    try:
        if not bool(load_settings().get("pushover_enabled", True)):
            print("Pushover disabled by settings")
            _log_delivery(title, False, "disabled by settings", has_url=bool(url))
            return False, "disabled by settings"
    except Exception as e:
        logging.warning("Silenced exception restored in v18.6.3: %s", e)
    """
    Sender Pushover-varsel.
    Bruker Render ENV:
    - PUSHOVER_APP_TOKEN
    - PUSHOVER_USER_KEY
    """
    if not pushover_enabled():
        print("Pushover ikke aktivert: mangler PUSHOVER_APP_TOKEN eller PUSHOVER_USER_KEY")
        _log_delivery(title, False, "missing env", has_url=bool(url))
        return False, "missing env"

    if _recent_duplicate(title, message, url):
        detail = "duplicate suppressed by durable fingerprint"
        print("Pushover duplikat undertrykt")
        _log_delivery(title, True, detail, has_url=bool(url))
        return True, detail

    try:
        payload = {
            "token": PUSHOVER_APP_TOKEN, "user": PUSHOVER_USER_KEY,
            "title": title, "message": message,
            # Pushover priority 1 is visible as high priority without the
            # acknowledgement/retry semantics of emergency priority 2.
            "priority": max(-2, min(1, int(priority or 0))),
        }
        if url:
            payload["url"] = str(url)
            payload["url_title"] = str(url_title or "Åpne rapport")
        response = requests.post("https://api.pushover.net/1/messages.json", data=payload, timeout=10)

        if response.status_code == 200:
            _record_notification_fingerprint(title, message, url)
            print("Pushover sendt")
            _log_delivery(title, True, "HTTP 200", has_url=bool(url))
            return True, None

        print(f"Pushover feil: {response.status_code} {response.text}")
        _log_delivery(title, False, f"HTTP {response.status_code}: {response.text}", has_url=bool(url))
        return False, response.text

    except Exception as e:
        print(f"Pushover exception: {e}")
        _log_delivery(title, False, str(e), has_url=bool(url))
        return False, str(e)


def notify_trade(trade_type, ticker, price, amount=None, shares=None, confidence=None, reason=None, pnl_pct=None, **details):
    """
    Sendes kun når faktisk trade er utført.
    Ikke ved vanlig signal/HOLD.
    """
    try:
        if not bool(load_settings().get("notify_paper_trades", True)):
            print("Paper trade-varsler deaktivert i settings")
            return False, "paper trade alerts disabled"
    except Exception as e:
        logging.warning("Silenced exception restored in v18.6.3: %s", e)

    trade_type = str(trade_type).upper()

    ticker = str(ticker or "-").upper()
    company = str(details.get("company_name") or details.get("name") or "").strip()
    title_identity = f"{ticker} · {company}" if company else ticker
    if trade_type == "BUY":
        icon = "📈"
        title = f"🔴 P1 · {title_identity} · PAPER BUY"
    elif trade_type == "SELL":
        icon = "📉"
        title = f"🔴 P1 · {title_identity} · PAPER SELL"
    else:
        icon = "🔔"
        title = f"🔴 P1 · {title_identity} · PAPER TRADE"

    exchange = str(details.get("exchange") or "").strip()
    country = str(details.get("country") or details.get("market") or "").strip()
    identity = " · ".join(value for value in (ticker, company, exchange, country) if value)
    lines = [f"PAPER – EID", f"{icon} {trade_type} {identity}"]
    entry_price = details.get("entry_price")
    exit_price = details.get("exit_price", price if trade_type == "SELL" else None)
    if trade_type == "SELL" and entry_price is not None:
        lines.extend([f"Kjøpskurs: {float(entry_price):.2f}", f"Salgskurs: {float(exit_price):.2f}"])
    else:
        lines.append(f"Pris: {float(price):.2f}")

    if amount is not None:
        lines.append(f"Beløp: {float(amount):,.0f} kr")

    if shares is not None:
        lines.append(f"Antall: {float(shares):.6f}")

    if confidence is not None:
        lines.append(f"Confidence: {confidence}%")

    if pnl_pct is not None:
        lines.append(f"Kursendring: {float(pnl_pct):+.2f}%")

    pnl_amount = details.get("pnl_amount", details.get("pnl"))
    if pnl_amount is not None and trade_type == "SELL":
        lines.append(f"Resultat: {float(pnl_amount):+,.2f} kr / {float(pnl_pct or 0):+.2f}%")
    if details.get("holding_time_known") is False:
        lines.append("Eiertid: ukjent – kjøpstidspunkt mangler")
    elif details.get("holding_days") is not None:
        lines.append(f"Eiertid: {int(details.get('holding_days') or 0)} børsdager")
    entry_score, exit_score = details.get("entry_score"), details.get("exit_score")
    if trade_type == "BUY" and entry_score is not None:
        lines.append(f"Score ved kjøp: {float(entry_score):.1f}")
    elif entry_score is not None or exit_score is not None:
        lines.append(f"Score: {float(entry_score or 0):.1f} → {float(exit_score or 0):.1f}")
    score_path = [float(value) for value in (details.get("score_path") or []) if value is not None]
    if score_path:
        lines.append("Scorebane: " + " → ".join(f"{value:.0f}" for value in score_path[-8:]))

    if reason:
        lines.append(f"Hovedårsak: {details.get('primary_sell_reason') or reason}")
    if details.get("contributing_reasons"):
        lines.append("Medvirkende: " + "; ".join(str(x) for x in details.get("contributing_reasons")[:2]))
    if details.get("replacement_ticker"):
        lines.append(f"Erstatter: {details.get('replacement_ticker')} · score {float(details.get('replacement_score') or 0):.1f}")
    industry = str(details.get("industry") or details.get("sector") or "").strip()
    if industry:
        lines.append(f"Bransje: {industry}")
    lines.append(f"Program: {_runtime_release_label()}")

    return send_pushover_alert("\n".join(lines), title=title, priority=1)
