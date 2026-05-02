from settings_store import load_settings

import os
import requests

PUSHOVER_APP_TOKEN = os.getenv("PUSHOVER_APP_TOKEN")
PUSHOVER_USER_KEY = os.getenv("PUSHOVER_USER_KEY")


def pushover_enabled():
    return bool(PUSHOVER_APP_TOKEN and PUSHOVER_USER_KEY)


def send_pushover_alert(message, title="AI Aksje Analyzer"):
    try:
        if not bool(load_settings().get("pushover_enabled", True)):
            print("Pushover disabled by settings")
            return False, "disabled by settings"
    except Exception:
        pass
    """
    Sender Pushover-varsel.
    Bruker Render ENV:
    - PUSHOVER_APP_TOKEN
    - PUSHOVER_USER_KEY
    """
    if not pushover_enabled():
        print("Pushover ikke aktivert: mangler PUSHOVER_APP_TOKEN eller PUSHOVER_USER_KEY")
        return False, "missing env"

    try:
        response = requests.post(
            "https://api.pushover.net/1/messages.json",
            data={
                "token": PUSHOVER_APP_TOKEN,
                "user": PUSHOVER_USER_KEY,
                "title": title,
                "message": message,
            },
            timeout=10,
        )

        if response.status_code == 200:
            print("Pushover sendt")
            return True, None

        print(f"Pushover feil: {response.status_code} {response.text}")
        return False, response.text

    except Exception as e:
        print(f"Pushover exception: {e}")
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
    except Exception:
        pass

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
