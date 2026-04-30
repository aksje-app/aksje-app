
from datetime import datetime
import json
from pathlib import Path

from broker_config import (
    REAL_TRADING_ENABLED,
    BROKER_MODE,
    REQUIRE_MANUAL_CONFIRM,
    EMERGENCY_STOP,
    MAX_ORDER_VALUE,
)

ORDER_LOG = Path("broker_order_log.json")


def _load_log():
    if not ORDER_LOG.exists():
        return []
    try:
        return json.loads(ORDER_LOG.read_text(encoding="utf-8"))
    except Exception:
        return []


def _save_log(rows):
    ORDER_LOG.write_text(json.dumps(rows, indent=2, ensure_ascii=False), encoding="utf-8")


def log_order(order):
    rows = _load_log()
    order["time"] = datetime.now().isoformat(timespec="seconds")
    rows.insert(0, order)
    _save_log(rows)


def get_order_log(limit=100):
    return _load_log()[:limit]


def validate_order(ticker, side, qty=None, notional=None, confirmed=False):
    ticker = str(ticker).upper().strip()
    side = str(side).lower().strip()

    if EMERGENCY_STOP:
        return False, "Emergency stop er aktiv"

    if side not in ["buy", "sell"]:
        return False, "Ugyldig side"

    if REQUIRE_MANUAL_CONFIRM and not confirmed:
        return False, "Manuell bekreftelse kreves"

    if notional is not None and float(notional) > MAX_ORDER_VALUE:
        return False, f"Ordrebeløp over maksgrense {MAX_ORDER_VALUE}"

    if not ticker:
        return False, "Ticker mangler"

    return True, "OK"


def place_order(ticker, side, qty=None, notional=None, confirmed=False):
    """
    Sikker broker-adapter.
    Standard er dry-run/paper. Ekte ordre sendes IKKE med mindre REAL_TRADING_ENABLED=true
    og emergency stop er av.
    """
    ok, reason = validate_order(ticker, side, qty, notional, confirmed)
    order = {
        "ticker": str(ticker).upper(),
        "side": side,
        "qty": qty,
        "notional": notional,
        "broker_mode": BROKER_MODE,
        "real_trading_enabled": REAL_TRADING_ENABLED,
        "status": "BLOCKED" if not ok else "DRY_RUN",
        "reason": reason,
    }

    if not ok:
        log_order(order)
        return False, reason

    if not REAL_TRADING_ENABLED:
        order["status"] = "DRY_RUN"
        order["reason"] = "Real trading er AV. Ingen ekte ordre sendt."
        log_order(order)
        return True, "Dry-run ordre logget. Ingen ekte ordre sendt."

    # LIVE gateway intentionally not implemented as automatic execution.
    # This prevents accidental real-money trading.
    if BROKER_MODE in ["alpaca_live", "alpaca_paper"]:
        order["status"] = "READY_NOT_SENT"
        order["reason"] = "Broker-adapter klar, men ekte ordre-sending er låst i denne versjonen."
        log_order(order)
        return False, "Broker-adapter klar, men sending er låst for sikkerhet."

    order["status"] = "UNKNOWN_MODE"
    order["reason"] = f"Ukjent broker mode: {BROKER_MODE}"
    log_order(order)
    return False, order["reason"]
