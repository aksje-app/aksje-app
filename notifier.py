import logging
from settings_store import load_settings

import os
import requests
from datetime import datetime, timezone
from storage_architecture import runtime_log_path
from durable_runtime import append_event, read_events

try:
    from runtime_env import load_app_env

    load_app_env()
except Exception:
    pass

PUSHOVER_APP_TOKEN = os.getenv("PUSHOVER_APP_TOKEN")
PUSHOVER_USER_KEY = os.getenv("PUSHOVER_USER_KEY")
PUSHOVER_AUDIT_PATH = runtime_log_path("pushover_audit.jsonl")


def _log_delivery(title, success, detail, *, has_url=False):
    append_event("notifications/pushover_audit.jsonl", PUSHOVER_AUDIT_PATH, {
        "at": datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds"),
        "channel": "PUSHOVER", "title": str(title), "success": bool(success),
        "detail": str(detail or "OK")[:500], "has_url": bool(has_url),
    })


def pushover_audit(limit=500):
    return read_events("notifications/pushover_audit.jsonl", PUSHOVER_AUDIT_PATH, limit=int(limit))


def pushover_enabled():
    return bool(PUSHOVER_APP_TOKEN and PUSHOVER_USER_KEY)


def send_pushover_alert(message, title="AI Aksje Analyzer", url=None, url_title=None):
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

    try:
        payload = {
            "token": PUSHOVER_APP_TOKEN, "user": PUSHOVER_USER_KEY,
            "title": title, "message": message,
        }
        if url:
            payload["url"] = str(url)
            payload["url_title"] = str(url_title or "Åpne rapport")
        response = requests.post("https://api.pushover.net/1/messages.json", data=payload, timeout=10)

        if response.status_code == 200:
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


def notify_trade(trade_type, ticker, price, amount=None, shares=None, confidence=None, reason=None, pnl_pct=None):
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

    if trade_type == "BUY":
        icon = "📈"
        title = "Paper BUY utført"
    elif trade_type == "SELL":
        icon = "📉"
        title = "Paper SELL utført"
    else:
        icon = "🔔"
        title = "Paper trade utført"

    lines = [
        f"{icon} {trade_type} {ticker}",
        f"Pris: {float(price):.2f}",
    ]

    if amount is not None:
        lines.append(f"Beløp: {float(amount):,.0f} kr")

    if shares is not None:
        lines.append(f"Antall: {float(shares):.6f}")

    if confidence is not None:
        lines.append(f"Confidence: {confidence}%")

    if pnl_pct is not None:
        lines.append(f"PnL: {float(pnl_pct):.2f}%")

    if reason:
        lines.append(f"Årsak: {reason}")

    return send_pushover_alert("\n".join(lines), title=title)
