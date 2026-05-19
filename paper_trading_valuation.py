"""Paper Trading valuation helpers.

Pure helper module used by UI and trading calculations so paper positions do
not show avg_price=0 or stale P/L when entry_price is present.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Mapping, Optional


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        if value is None or value == "":
            return float(default)
        return float(value)
    except Exception:
        return float(default)


def paper_reason_label(reason: Any, trade_type: str = "") -> str:
    text = str(reason or "").strip()
    if not text:
        return ""
    lowered = text.lower()
    if "auto buy" in lowered:
        text = text.replace("AUTO BUY", "PAPER-KJØP")
    if "ui kjøp nå" in lowered or "ui kjÃ¸p nÃ¥" in lowered:
        text = text.replace("UI Kjøp nå", "PAPER-KJØP").replace("UI KjÃ¸p nÃ¥", "PAPER-KJØP")
    if "kjøp nå" in lowered or "kjÃ¸p nÃ¥" in lowered:
        text = text.replace("Kjøp nå", "Kjøp-nå").replace("KjÃ¸p nÃ¥", "Kjøp-nå")
    if trade_type.upper() == "BUY" and not text.upper().startswith("PAPER"):
        text = f"PAPER-KJØP: {text}"
    if trade_type.upper() == "SELL" and not text.upper().startswith("PAPER"):
        text = f"PAPER-SALG: {text}"
    return text


def normalize_paper_position(
    ticker: Any,
    pos: Mapping[str, Any] | None,
    *,
    latest_price: Optional[float] = None,
    updated_at: str = "",
) -> Dict[str, Any]:
    row = dict(pos or {})
    symbol = str(row.get("ticker") or ticker or "").upper().strip()
    shares = _safe_float(row.get("shares", row.get("units", 0)), 0.0)
    stored_last = _safe_float(row.get("last_price"), 0.0)
    entry = _safe_float(row.get("avg_price"), 0.0)
    if entry <= 0:
        entry = _safe_float(row.get("entry_price"), 0.0)
    if entry <= 0:
        entry = _safe_float(row.get("price"), 0.0)

    last = _safe_float(latest_price, 0.0) if latest_price is not None else stored_last
    if last <= 0:
        last = entry
    if entry <= 0:
        entry = last

    value = shares * last
    cost = shares * entry
    pnl = value - cost
    pnl_pct = ((last - entry) / entry * 100.0) if entry else 0.0
    highest = max(_safe_float(row.get("highest_price"), 0.0), last, entry)

    row.update({
        "ticker": symbol,
        "shares": shares,
        "units": shares,
        "entry_price": entry,
        "avg_price": entry,
        "last_price": last,
        "highest_price": highest,
        "market_value": value,
        "cost_basis": cost,
        "unrealized_pnl": pnl,
        "pnl_pct": pnl_pct,
    })
    if updated_at:
        row["last_price_updated_at"] = updated_at
    row.setdefault("asset_type", "Aksje")
    row.setdefault("units_label", row.get("unit_label") or "shares")
    row["reason"] = paper_reason_label(row.get("reason"), "BUY")
    return row


def normalize_paper_portfolio(
    portfolio: Mapping[str, Any] | None,
    latest_prices: Mapping[str, Any] | None = None,
    *,
    updated_at: str = "",
) -> Dict[str, Any]:
    latest_prices = latest_prices or {}
    out = dict(portfolio or {})
    positions: Dict[str, Dict[str, Any]] = {}
    for ticker, pos in (out.get("positions", {}) or {}).items():
        symbol = str(ticker or (pos or {}).get("ticker") or "").upper().strip()
        latest = latest_prices.get(symbol, latest_prices.get(ticker))
        positions[symbol] = normalize_paper_position(symbol, pos, latest_price=latest, updated_at=updated_at)
    out["positions"] = positions
    out.setdefault("cash", 0.0)
    out.setdefault("trades", [])
    return out


def paper_position_rows(portfolio: Mapping[str, Any] | None, latest_prices: Mapping[str, Any] | None = None) -> List[Dict[str, Any]]:
    normalized = normalize_paper_portfolio(portfolio, latest_prices)
    rows: List[Dict[str, Any]] = []
    for ticker, pos in normalized.get("positions", {}).items():
        rows.append({
            "ticker": ticker,
            "type": pos.get("asset_type", "Aksje"),
            "units": round(_safe_float(pos.get("shares")), 4),
            "unit_label": pos.get("units_label", "shares"),
            "avg_price": round(_safe_float(pos.get("avg_price")), 4),
            "last_price": round(_safe_float(pos.get("last_price")), 4),
            "value": round(_safe_float(pos.get("market_value")), 2),
            "currency": pos.get("currency", ""),
            "pnl_pct": round(_safe_float(pos.get("pnl_pct")), 2),
            "pnl": round(_safe_float(pos.get("unrealized_pnl")), 2),
            "updated": pos.get("last_price_updated_at", ""),
        })
    return rows


def paper_trade_rows(trades: Any, limit: int = 50) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    for trade in list(trades or [])[: max(1, int(limit or 50))]:
        if not isinstance(trade, Mapping):
            continue
        row = dict(trade)
        row["type"] = "PAPER-KJØP" if str(row.get("type", "")).upper() == "BUY" else ("PAPER-SALG" if str(row.get("type", "")).upper() == "SELL" else row.get("type", ""))
        row["reason"] = paper_reason_label(row.get("reason"), str(trade.get("type", "")))
        rows.append(row)
    return rows


def timestamp_now() -> str:
    return datetime.now().isoformat(timespec="seconds")
