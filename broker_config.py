
import os

REAL_TRADING_ENABLED = os.getenv("REAL_TRADING_ENABLED", "false").lower() == "true"
BROKER_MODE = os.getenv("BROKER_MODE", "paper").lower()
REQUIRE_MANUAL_CONFIRM = os.getenv("REQUIRE_MANUAL_CONFIRM", "true").lower() == "true"
EMERGENCY_STOP = os.getenv("EMERGENCY_STOP", "true").lower() == "true"
MAX_ORDER_VALUE = float(os.getenv("MAX_ORDER_VALUE", "1000"))

ALPACA_API_KEY = os.getenv("ALPACA_API_KEY", "")
ALPACA_SECRET_KEY = os.getenv("ALPACA_SECRET_KEY", "")
ALPACA_BASE_URL = os.getenv("ALPACA_BASE_URL", "https://paper-api.alpaca.markets")


def broker_status():
    if EMERGENCY_STOP:
        return "🛑 Emergency stop aktiv"

    if not REAL_TRADING_ENABLED:
        return "🧪 Real trading AV - dry run/paper only"

    if BROKER_MODE == "alpaca_paper":
        return "🟡 Alpaca paper broker klar"

    if BROKER_MODE == "alpaca_live":
        return "🔴 Alpaca LIVE valgt"

    return f"⚪ Broker mode: {BROKER_MODE}"
