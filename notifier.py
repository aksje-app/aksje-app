
from settings_store import load_settings

import os
import requests


def _get_pushover_token():
    return (
        os.getenv("PUSHOVER_APP_TOKEN")
        or os.getenv("PUSHOVER_API_TOKEN")
        or os.getenv("PUSHOVER_TOKEN")
        or ""
    ).strip()


def _get_pushover_user():
    return (
        os.getenv("PUSHOVER_USER_KEY")
        or os.getenv("PUSHOVER_USER")
        or ""
    ).strip()


def pushover_enabled():
    return bool(_get_pushover_token() and _get_pushover_user())


def send_pushover_alert(message, title="AI Aksje Analyzer"):
    try:
        if not bool(load_settings().get("pushover_enabled", True)):
            print("Pushover disabled by settings")
            return False, "disabled by settings"
    except Exception:
        pass

    token = _get_pushover_token()
    user = _get_pushover_user()

    if not token or not user:
        print("Pushover ikke aktivert: mangler PUSHOVER_APP_TOKEN/PUSHOVER_API_TOKEN eller PUSHOVER_USER_KEY")
        return False, "missing env"

    try:
        response = requests.post(
            "https://api.pushover.net/1/messages.json",
            data={
                "token": token,
                "user": user,
                "title": title,
                "message": message,
            },
            timeout=15,
        )

        if response.status_code == 200:
            print("Pushover sendt")
            return True, None

        print(f"Pushover feil: {response.status_code} {response.text}")
        return False, response.text

    except Exception as e:
        print(f"Pushover exception: {e}")
        return False, str(e)


def notify_trade(trade_type, ticker=None, price=None, amount=None, shares=None, confidence=None, reason=None, pnl_pct=None, title=None):
    """
    Robust trade-varsel.

    Støtter begge kall:
    - notify_trade("BUY", ticker, price, ...)
    - notify_trade("ferdig formattert melding")
    """
    # Backwards compatibility: if called with one formatted message
    if ticker is None and price is None:
        return send_pushover_alert(str(trade_type), title=title or "AI Aksje Analyzer - Trade")

    trade_type = str(trade_type).upper()

    if trade_type == "BUY":
        icon = "📈"
        msg_title = title or "Paper BUY utført"
    elif trade_type == "SELL":
        icon = "📉"
        msg_title = title or "Paper SELL utført"
    else:
        icon = "🔔"
        msg_title = title or "Paper trade utført"

    lines = [
        f"{icon} {trade_type} {ticker}",
        f"Pris: {float(price):.2f}",
    ]

    if amount is not None:
        lines.append(f"Beløp: {float(amount):,.2f}")
    if shares is not None:
        lines.append(f"Antall: {float(shares):.6f}")
    if confidence is not None:
        lines.append(f"Confidence: {int(confidence)}%")
    if pnl_pct is not None:
        lines.append(f"PnL: {float(pnl_pct):.2f}%")
    if reason:
        lines.append(f"Årsak: {reason}")

    return send_pushover_alert("\n".join(lines), title=msg_title)
