"""Paper Trading valuation helpers.

Pure helper module used by UI and trading calculations so paper positions do
not show avg_price=0 or stale P/L when entry_price is present.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Mapping, Optional

PAPER_SHARED_COLUMNS = [
    "Tid",
    "Status",
    "Type",
    "Ticker",
    "Navn",
    "Land",
    "Marked",
    "Sektor",
    "Bransje",
    "Aktivatype",
    "Valuta",
    "Snittkurs/NAV",
    "Siste kurs/NAV",
    "Pris",
    "Antall",
    "Beløp/verdi",
    "P/L kr",
    "P/L %",
    "Vekt %",
    "Confidence",
    "Kilde/signal",
    "Regel",
    "Grense",
    "Målt verdi",
    "Forklaring",
    "Oppdatert",
]


def _security_context_from_ticker(ticker: Any, row: Mapping[str, Any] | None = None) -> Dict[str, str]:
    """Best-effort local metadata for rows created before metadata logging existed."""
    raw = dict(row or {}) if isinstance(row, Mapping) else {}
    symbol = str(raw.get("ticker") or ticker or "").strip().upper()
    if not symbol:
        return {"country": "", "market": "", "sector": "", "industry": ""}
    try:
        from security_metadata import infer_security_listing, resolve_security_metadata

        meta = resolve_security_metadata(symbol, raw)
        listing = infer_security_listing(symbol, meta)
        sector = str(raw.get("sector") or meta.get("sector") or "").strip()
        industry = str(raw.get("industry") or raw.get("bransje") or sector or "").strip()
        return {
            "country": str(raw.get("country") or raw.get("land") or listing.get("country") or "").strip(),
            "market": str(raw.get("market") or listing.get("market") or "").strip(),
            "sector": sector,
            "industry": industry,
        }
    except Exception:
        if symbol.endswith(".OL"):
            return {"country": "Norge", "market": "Norge", "sector": "", "industry": ""}
        if symbol.endswith(".ST"):
            return {"country": "Sverige", "market": "Sverige", "sector": "", "industry": ""}
        if symbol.endswith(".CO"):
            return {"country": "Danmark", "market": "Danmark", "sector": "", "industry": ""}
        if symbol.endswith(".HE"):
            return {"country": "Finland", "market": "Finland", "sector": "", "industry": ""}
        if symbol.endswith(".SA"):
            return {"country": "Brasil", "market": "Brasil", "sector": "", "industry": ""}
        return {"country": "USA", "market": "USA", "sector": "", "industry": ""}


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
        context = _security_context_from_ticker(ticker, pos)
        rows.append({
            "ticker": ticker,
            "type": pos.get("asset_type", "Aksje"),
            "land": pos.get("country", "") or context.get("country", ""),
            "marked": pos.get("market", "") or context.get("market", ""),
            "sektor": pos.get("sector", "") or context.get("sector", ""),
            "bransje": pos.get("industry", "") or pos.get("sector", "") or context.get("industry", ""),
            "units": round(_safe_float(pos.get("shares")), 4),
            "unit_label": pos.get("units_label", "shares"),
            "avg_price": round(_safe_float(pos.get("avg_price")), 4),
            "last_price": round(_safe_float(pos.get("last_price")), 4),
            "value": round(_safe_float(pos.get("market_value")), 2),
            "currency": pos.get("currency", ""),
            "pnl_pct": round(_safe_float(pos.get("pnl_pct")), 2),
            "pnl": round(_safe_float(pos.get("unrealized_pnl")), 2),
            "updated": pos.get("last_price_updated_at", ""),
            "confidence": int(_safe_float(pos.get("confidence"), 0)),
            "reason": pos.get("reason", ""),
            "name": pos.get("name", "") or pos.get("company", ""),
            "status": "Åpen",
        })
    return rows


def paper_position_display_rows(
    portfolio: Mapping[str, Any] | None,
    latest_prices: Mapping[str, Any] | None = None,
    *,
    total_value: float | None = None,
) -> List[Dict[str, Any]]:
    base_rows = paper_position_rows(portfolio, latest_prices)
    if total_value is None:
        total_value = sum(_safe_float(row.get("value"), 0.0) for row in base_rows)
    out: List[Dict[str, Any]] = []
    for row in base_rows:
        value = _safe_float(row.get("value"), 0.0)
        weight = (value / total_value * 100.0) if total_value else 0.0
        out.append({
            "Tid": row.get("updated") or "",
            "Status": "Åpen",
            "Type": "Beholdning",
            "Ticker": row.get("ticker", ""),
            "Navn": row.get("name", ""),
            "Land": row.get("land", ""),
            "Marked": row.get("marked", ""),
            "Sektor": row.get("sektor", ""),
            "Bransje": row.get("bransje", ""),
            "Aktivatype": row.get("type", "Aksje"),
            "Valuta": row.get("currency", ""),
            "Snittkurs/NAV": row.get("avg_price", ""),
            "Siste kurs/NAV": row.get("last_price", ""),
            "Pris": row.get("last_price", ""),
            "Antall": row.get("units", ""),
            "Beløp/verdi": round(value, 2),
            "P/L kr": row.get("pnl", ""),
            "P/L %": row.get("pnl_pct", ""),
            "Vekt %": round(weight, 1),
            "Confidence": row.get("confidence", ""),
            "Kilde/signal": row.get("reason", ""),
            "Regel": "",
            "Grense": "",
            "Målt verdi": "",
            "Forklaring": "Åpen paper-posisjon beregnet fra beholdning, siste kurs og snittpris.",
            "Oppdatert": row.get("updated") or "Lagret kurs",
        })
    return out


def paper_trade_rows(trades: Any, limit: int = 50) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    preferred_order = [
        "time", "type", "ticker", "land", "marked", "sektor", "bransje",
        "price", "shares", "amount", "confidence", "pnl_pct",
        "reason", "regel", "grense", "maalt_verdi", "hvorfor",
        "asset_type", "currency", "nav_date", "order_kind",
    ]
    for trade in list(trades or [])[: max(1, int(limit or 50))]:
        if not isinstance(trade, Mapping):
            continue
        row = dict(trade)
        context = _security_context_from_ticker(row.get("ticker"), row)
        row["type"] = "PAPER-KJØP" if str(row.get("type", "")).upper() == "BUY" else ("PAPER-SALG" if str(row.get("type", "")).upper() == "SELL" else row.get("type", ""))
        row["reason"] = paper_reason_label(row.get("reason"), str(trade.get("type", "")))
        row["land"] = row.get("country", "") or context.get("country", "")
        row["marked"] = row.get("market", "") or context.get("market", "")
        row["sektor"] = row.get("sector", "") or context.get("sector", "")
        row["bransje"] = row.get("industry", "") or row.get("sector", "") or context.get("industry", "")
        row["regel"] = row.get("rule_used", "")
        row["grense"] = row.get("rule_limit", "")
        row["maalt_verdi"] = row.get("measured_value", "")
        row["hvorfor"] = row.get("trade_explanation", "")
        ordered = {key: row.get(key, "") for key in preferred_order if key in row}
        for key, value in row.items():
            if key not in ordered and key not in {"country", "market", "sector", "industry", "rule_used", "rule_limit", "measured_value", "trade_explanation"}:
                ordered[key] = value
        rows.append(ordered)
    return rows


def paper_trade_display_rows(trades: Any, limit: int = 50) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    for row in paper_trade_rows(trades, limit=limit):
        trade_type = str(row.get("type") or "")
        out.append({
            "Tid": row.get("time", ""),
            "Status": "Historisk",
            "Type": trade_type,
            "Ticker": row.get("ticker", ""),
            "Navn": row.get("name", ""),
            "Land": row.get("land", ""),
            "Marked": row.get("marked", ""),
            "Sektor": row.get("sektor", ""),
            "Bransje": row.get("bransje", ""),
            "Aktivatype": row.get("asset_type", "") or "Aksje",
            "Valuta": row.get("currency", ""),
            "Snittkurs/NAV": row.get("avg_price", "") or row.get("price", ""),
            "Siste kurs/NAV": row.get("last_price", "") or row.get("price", ""),
            "Pris": row.get("price", ""),
            "Antall": row.get("shares", ""),
            "Beløp/verdi": row.get("amount", ""),
            "P/L kr": row.get("pnl", ""),
            "P/L %": row.get("pnl_pct", ""),
            "Vekt %": "",
            "Confidence": row.get("confidence", ""),
            "Kilde/signal": row.get("reason", ""),
            "Regel": row.get("regel", ""),
            "Grense": row.get("grense", ""),
            "Målt verdi": row.get("maalt_verdi", ""),
            "Forklaring": row.get("hvorfor", ""),
            "Oppdatert": row.get("time", ""),
        })
    return out


def timestamp_now() -> str:
    return datetime.now().isoformat(timespec="seconds")
