"""
ai_heatmap_engine.py

v18.4.3 AI Heatmaps & Risk Visualization

Lager fargekodet risikovisning fra lagrede prognoser, varsler og appdata.
Ingen auto-trading-kobling.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

from forecast_store import load_forecast_log, load_alerts


def _risk_level_from_row(row: Dict[str, Any]) -> str:
    strength = int(row.get("strength", 0))
    confidence = int(row.get("confidence", 0))
    bear_pct = float(row.get("bear_pct", 0))
    risk = str(row.get("risk", ""))

    if risk == "Høy" or strength < 35 or confidence < 40 or bear_pct <= -10:
        return "red"
    if strength < 55 or confidence < 55 or bear_pct <= -5 or risk == "Medium":
        return "yellow"
    return "green"


def _risk_label(level: str) -> str:
    return {"red": "Høy risiko", "yellow": "Middels", "green": "Sterk/lav risiko"}.get(level, "Ukjent")


def _extract_latest_forecast_rows(limit: int = 500) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    try:
        for payload in load_forecast_log(limit=limit):
            ticker = str(payload.get("ticker", "")).upper()
            saved_at = payload.get("saved_at") or payload.get("generated_at", "")
            for horizon, item in payload.get("horizons", {}).items():
                summary = item.get("summary", {})
                if not summary:
                    continue
                rows.append({
                    "ticker": ticker,
                    "horizon": horizon,
                    "saved_at": saved_at,
                    "base_pct": float(summary.get("base_pct", 0)),
                    "bull_pct": float(summary.get("bull_pct", 0)),
                    "bear_pct": float(summary.get("bear_pct", 0)),
                    "confidence": int(summary.get("confidence", 0)),
                    "strength": int(summary.get("forecast_strength", 0)),
                    "risk": summary.get("risk", ""),
                    "label": summary.get("forecast_strength_label", ""),
                })
    except Exception:
        return []

    latest: Dict[Tuple[str, str], Dict[str, Any]] = {}
    for row in rows:
        latest[(row["ticker"], row["horizon"])] = row
    return list(latest.values())


def build_heatmap_rows(source_tickers: Optional[List[str]] = None, limit: int = 200) -> List[Dict[str, Any]]:
    """Build normalized heatmap rows from forecast log and optional ticker filter."""
    rows = _extract_latest_forecast_rows(limit=limit)
    if source_tickers:
        allowed = {str(t).upper() for t in source_tickers}
        rows = [r for r in rows if r.get("ticker") in allowed]

    alerts_by_ticker: Dict[str, int] = {}
    try:
        for alert in load_alerts(limit=300):
            ticker = str(alert.get("ticker", "")).upper()
            if not ticker:
                continue
            weight = {"red": 3, "yellow": 2, "green": 1}.get(str(alert.get("level", "")).lower(), 1)
            alerts_by_ticker[ticker] = alerts_by_ticker.get(ticker, 0) + weight
    except Exception:
        pass

    out: List[Dict[str, Any]] = []
    for row in rows:
        level = _risk_level_from_row(row)
        ticker = row.get("ticker", "")
        out.append({
            **row,
            "risk_level": level,
            "risk_label": _risk_label(level),
            "alert_weight": alerts_by_ticker.get(ticker, 0),
        })

    out.sort(key=lambda r: (
        {"red": 3, "yellow": 2, "green": 1}.get(r.get("risk_level"), 0),
        r.get("alert_weight", 0),
        -r.get("strength", 0),
    ), reverse=True)
    return out


def summarize_heatmap(rows: List[Dict[str, Any]]) -> Dict[str, Any]:
    counts = {"red": 0, "yellow": 0, "green": 0}
    for row in rows:
        level = row.get("risk_level", "yellow")
        if level in counts:
            counts[level] += 1
    total = len(rows)
    avg_strength = round(sum(r.get("strength", 0) for r in rows) / total, 1) if total else 0
    avg_confidence = round(sum(r.get("confidence", 0) for r in rows) / total, 1) if total else 0
    return {
        "total": total,
        "counts": counts,
        "avg_strength": avg_strength,
        "avg_confidence": avg_confidence,
    }


def extract_tickers_from_app_state(session_state: Any, keys: Optional[List[str]] = None) -> List[str]:
    """Extract tickers from session_state sources like portfolio/watchlist/ranking."""
    keys = keys or ["portfolio", "paper_portfolio", "holdings", "positions", "watchlist", "top_picks", "ai_ranking"]
    tickers: List[str] = []

    def add(value: Any) -> None:
        if value is None:
            return
        if isinstance(value, str):
            s = value.strip().upper()
            if 1 <= len(s) <= 24 and all(ch.isalnum() or ch in ".-_" for ch in s):
                if s not in tickers:
                    tickers.append(s)
        elif isinstance(value, dict):
            for k in ("ticker", "symbol", "Ticker", "Symbol"):
                if k in value:
                    add(value.get(k))
            for k, v in value.items():
                add(k)
                add(v)
        elif isinstance(value, list):
            for item in value:
                add(item)

    try:
        for key in keys:
            if key in session_state:
                add(session_state.get(key))
    except Exception:
        pass

    return tickers[:100]


def infer_sector_from_ticker(ticker: str) -> str:
    """Simple sector/group inference for first treemap version."""
    t = (ticker or "").upper()
    tech = {"AAPL", "MSFT", "NVDA", "AMD", "AVGO", "TSLA", "META", "GOOGL", "GOOG", "AMZN", "NFLX", "PLTR", "ORCL", "CRM", "ADBE", "INTC", "SMCI"}
    energy = {"XOM", "CVX", "COP", "EQNR", "EQNR.OL", "AKRBP.OL", "SHEL", "BP", "TTE"}
    finance = {"JPM", "BAC", "WFC", "GS", "MS", "C", "V", "MA", "AXP", "DNB.OL"}
    health = {"UNH", "LLY", "JNJ", "PFE", "MRK", "ABBV", "NVO", "NOVO-B.CO"}
    industrial = {"CAT", "DE", "GE", "BA", "MMM", "HON", "LMT", "RTX"}
    consumer = {"KO", "PEP", "MCD", "NKE", "SBUX", "WMT", "COST", "HD"}
    crypto = {"BTC-USD", "ETH-USD", "SOL-USD"}

    if t in tech:
        return "Tech / AI"
    if t in energy:
        return "Energy"
    if t in finance:
        return "Finance"
    if t in health:
        return "Health"
    if t in industrial:
        return "Industrial"
    if t in consumer:
        return "Consumer"
    if t in crypto:
        return "Crypto"
    if t.endswith(".OL") or t.endswith(".CO") or t.endswith(".ST"):
        return "Nordic"
    return "Other"


def build_matrix_payload(rows: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Build matrix heatmap payload: tickers x horizons with strength/risk values."""
    tickers = []
    horizons = []
    for row in rows:
        t = row.get("ticker")
        h = row.get("horizon")
        if t and t not in tickers:
            tickers.append(t)
        if h and h not in horizons:
            horizons.append(h)

    horizon_order = ["1d", "1w", "1m", "3m", "6m"]
    horizons = sorted(horizons, key=lambda h: horizon_order.index(h) if h in horizon_order else 99)

    lookup = {(r.get("ticker"), r.get("horizon")): r for r in rows}
    z = []
    text = []
    for ticker in tickers:
        z_row = []
        text_row = []
        for horizon in horizons:
            row = lookup.get((ticker, horizon))
            if row:
                strength = int(row.get("strength", 0))
                bear = float(row.get("bear_pct", 0))
                conf = int(row.get("confidence", 0))
                z_row.append(strength)
                text_row.append(f"{ticker} {horizon}<br>Strength {strength}/100<br>Confidence {conf}%<br>Bear {bear:+.2f}%")
            else:
                z_row.append(None)
                text_row.append("")
        z.append(z_row)
        text.append(text_row)

    return {"tickers": tickers, "horizons": horizons, "z": z, "text": text}


def build_sector_treemap_rows(rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Aggregate forecast rows by inferred sector/group for treemap."""
    groups: Dict[str, Dict[str, Any]] = {}
    for row in rows:
        ticker = row.get("ticker", "")
        sector = infer_sector_from_ticker(ticker)
        g = groups.setdefault(sector, {
            "sector": sector,
            "count": 0,
            "strength_sum": 0.0,
            "confidence_sum": 0.0,
            "red": 0,
            "yellow": 0,
            "green": 0,
            "bear_sum": 0.0,
        })
        g["count"] += 1
        g["strength_sum"] += float(row.get("strength", 0))
        g["confidence_sum"] += float(row.get("confidence", 0))
        g["bear_sum"] += float(row.get("bear_pct", 0))
        level = row.get("risk_level", "yellow")
        if level in ("red", "yellow", "green"):
            g[level] += 1

    out = []
    for sector, g in groups.items():
        count = max(1, int(g["count"]))
        avg_strength = round(g["strength_sum"] / count, 1)
        avg_conf = round(g["confidence_sum"] / count, 1)
        avg_bear = round(g["bear_sum"] / count, 2)
        risk_pressure = g["red"] * 3 + g["yellow"] * 1.5
        out.append({
            "sector": sector,
            "count": count,
            "avg_strength": avg_strength,
            "avg_confidence": avg_conf,
            "avg_bear_pct": avg_bear,
            "red": g["red"],
            "yellow": g["yellow"],
            "green": g["green"],
            "risk_pressure": round(risk_pressure, 1),
        })

    out.sort(key=lambda x: (x["risk_pressure"], -x["avg_strength"]), reverse=True)
    return out
