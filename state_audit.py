"""v18.5.88 State & Audit helpers.

Small helpers that describe committed paper-trading state without importing
Streamlit or analysis modules. Used as a safe layer around trading actions.
"""
from __future__ import annotations
from utils import _safe_float  # v18.6.3 centralized helpers

from dataclasses import dataclass, asdict
from datetime import datetime
from typing import Any, Dict, Optional, Tuple

try:
    from safety_audit import add_audit_event
except Exception:  # pragma: no cover - fail-safe import
    def add_audit_event(event: str, detail: Optional[Dict[str, Any]] = None, *, level: str = "INFO"):
        return {"event": event, "detail": detail or {}, "level": level}


@dataclass(frozen=True)
class PaperStateSnapshot:
    ts: str
    cash: float
    buying_power: float
    positions_value: float
    total_value: float
    open_positions: int
    trades_count: int
    buys_today: int
    max_buys_per_day: int




def _today_iso() -> str:
    return datetime.now().date().isoformat()


def _position_value(portfolio: Dict[str, Any], latest_prices: Optional[Dict[str, Any]] = None) -> float:
    latest_prices = latest_prices or {}
    total = 0.0
    for ticker, pos in (portfolio or {}).get("positions", {}).items():
        if not isinstance(pos, dict):
            continue
        shares = _safe_float(pos.get("shares", pos.get("units", 0)))
        fallback = pos.get("last_price", pos.get("entry_price", pos.get("avg_price", 0)))
        price = _safe_float(latest_prices.get(ticker, fallback))
        total += shares * price
    return round(total, 2)


def count_buys_today(portfolio: Dict[str, Any]) -> int:
    today = _today_iso()
    count = 0
    for trade in (portfolio or {}).get("trades", []) or []:
        if str(trade.get("time", "")).startswith(today) and str(trade.get("type", "")).upper() == "BUY":
            count += 1
    return count


def build_paper_state_snapshot(portfolio: Optional[Dict[str, Any]], latest_prices: Optional[Dict[str, Any]] = None, rules: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    portfolio = portfolio or {}
    rules = rules or {}
    cash = round(_safe_float(portfolio.get("cash", 0)), 2)
    positions_value = _position_value(portfolio, latest_prices)
    snap = PaperStateSnapshot(
        ts=datetime.now().isoformat(timespec="seconds"),
        cash=cash,
        buying_power=round(max(0.0, cash), 2),
        positions_value=positions_value,
        total_value=round(cash + positions_value, 2),
        open_positions=len((portfolio or {}).get("positions", {}) or {}),
        trades_count=len((portfolio or {}).get("trades", []) or []),
        buys_today=count_buys_today(portfolio),
        max_buys_per_day=int(rules.get("max_trades_per_day", rules.get("max_buys_per_day", 3)) or 3),
    )
    return asdict(snap)


def validate_buy_order(
    portfolio: Dict[str, Any],
    *,
    ticker: str,
    price: float,
    amount: float,
    confidence: int = 0,
    min_confidence: int = 0,
    allow_existing: bool = False,
    max_open_positions: Optional[int] = None,
    max_buys_per_day: Optional[int] = None,
    safety_mode: bool = True,
) -> Tuple[bool, str]:
    """Central fail-safe for paper BUY actions.

    It validates committed state only. It never mutates the portfolio.
    """
    ticker = str(ticker or "").strip().upper()
    if not ticker:
        return False, "Mangler ticker/symbol"
    if _safe_float(price) <= 0:
        return False, "Ugyldig prisdata - kjøp stoppet"
    if _safe_float(amount) <= 0:
        return False, "Beløp må være større enn 0"
    if not isinstance(portfolio, dict) or not isinstance(portfolio.get("positions", {}), dict):
        return False, "Sikkerhetsmodus: ugyldig porteføljedata - kjøp stoppet"

    positions = portfolio.get("positions", {}) or {}
    cash = _safe_float(portfolio.get("cash", 0))
    if cash < _safe_float(amount):
        return False, f"Ikke nok cash ({cash:.2f} tilgjengelig)"
    if safety_mode and cash <= 0:
        return False, "Sikkerhetsmodus: ingen tilgjengelig cash - kjøp stoppet"
    if safety_mode and _safe_float(amount) > cash:
        return False, "Sikkerhetsmodus: kjøp overstiger tilgjengelig cash"
    if not allow_existing and ticker in positions:
        return False, f"{ticker} eies allerede"
    if max_open_positions is not None and not allow_existing and len(positions) >= int(max_open_positions):
        return False, (
            f"Maks åpne posisjoner nådd: {len(positions)} av {int(max_open_positions)} brukt. "
            "Dette er aktiv regel fra trading_settings akkurat nå. Hvis UI viser en annen grense, "
            "er innstillingen ikke aktivert/lagret, eller en eldre regel brukes i runtime."
        )
    if int(confidence or 0) < int(min_confidence or 0):
        return False, f"Confidence for lav ({int(confidence or 0)} < {int(min_confidence or 0)})"
    if max_buys_per_day is not None and count_buys_today(portfolio) >= int(max_buys_per_day):
        return False, f"Maks kjøp per dag nådd ({int(max_buys_per_day)})"
    return True, "OK"


def audit_state_transition(event: str, before: Dict[str, Any], after: Optional[Dict[str, Any]] = None, detail: Optional[Dict[str, Any]] = None, *, level: str = "INFO") -> Dict[str, Any]:
    payload = {"before": before, "after": after or {}, "detail": detail or {}}
    return add_audit_event(event, payload, level=level)
