"""
forecast_store.py

Fase 6-10 støttefunksjoner:
- lagre prognoser
- lese siste prognoser
- enkel prognose-backtest mot faktisk kurs
- varselregler
- daglig oppdateringsstruktur

Ingen auto-trading-kobling.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

from forecast_engine import build_all_horizons


DATA_DIR = Path("data")
FORECAST_DIR = DATA_DIR / "forecasts"
FORECAST_LOG = FORECAST_DIR / "forecast_log.jsonl"
FORECAST_ALERTS = FORECAST_DIR / "forecast_alerts.jsonl"


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def ensure_forecast_dirs() -> None:
    FORECAST_DIR.mkdir(parents=True, exist_ok=True)


def _safe_ticker(ticker: str) -> str:
    return "".join(ch for ch in ticker.upper() if ch.isalnum() or ch in ".-_")[:24] or "UNKNOWN"


def save_forecast_result(ticker: str, payload: Dict[str, Any]) -> Path:
    """Save latest all-horizon forecast for a ticker and append to log."""
    ensure_forecast_dirs()
    ticker_safe = _safe_ticker(ticker)
    payload = dict(payload)
    payload["saved_at"] = _now_iso()

    latest_path = FORECAST_DIR / f"{ticker_safe}_latest.json"
    latest_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    with FORECAST_LOG.open("a", encoding="utf-8") as f:
        f.write(json.dumps(payload, ensure_ascii=False) + "\n")

    return latest_path


def load_latest_forecast(ticker: str) -> Optional[Dict[str, Any]]:
    ensure_forecast_dirs()
    path = FORECAST_DIR / f"{_safe_ticker(ticker)}_latest.json"
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


def load_forecast_log(limit: int = 200) -> List[Dict[str, Any]]:
    ensure_forecast_dirs()
    if not FORECAST_LOG.exists():
        return []
    rows: List[Dict[str, Any]] = []
    try:
        lines = FORECAST_LOG.read_text(encoding="utf-8").splitlines()
        for line in lines[-limit:]:
            try:
                rows.append(json.loads(line))
            except Exception:
                continue
    except Exception:
        return []
    return rows


def build_and_store_all_horizons(
    ticker: str,
    prices: Sequence[float],
    *,
    ai_score: Optional[float] = None,
    sentiment_score: Optional[float] = None,
) -> Dict[str, Any]:
    """Build all horizon forecasts and persist them."""
    result = build_all_horizons(ticker, prices, ai_score=ai_score, sentiment_score=sentiment_score)
    payload = {
        "ticker": ticker.upper(),
        "generated_at": _now_iso(),
        "ai_score": ai_score,
        "sentiment_score": sentiment_score,
        "horizons": result,
    }
    save_forecast_result(ticker, payload)
    return payload


def evaluate_forecast_accuracy(
    forecast_payload: Dict[str, Any],
    actual_price: float,
    horizon: str,
) -> Dict[str, Any]:
    """Compare forecast against an actual price for one horizon."""
    ticker = forecast_payload.get("ticker", "UNKNOWN")
    horizons = forecast_payload.get("horizons", {})
    item = horizons.get(horizon)
    if not item:
        raise ValueError(f"Mangler horisont i forecast payload: {horizon}")

    summary = item.get("summary", {})
    base_price = float(summary.get("base_price", 0))
    bull_price = float(summary.get("bull_price", 0))
    bear_price = float(summary.get("bear_price", 0))
    current_price = float(summary.get("current_price", 0))
    actual = float(actual_price)

    if base_price <= 0 or current_price <= 0:
        raise ValueError("Forecast mangler gyldige priser.")

    error_pct = (actual / base_price - 1.0) * 100.0
    actual_return_pct = (actual / current_price - 1.0) * 100.0
    base_return_pct = (base_price / current_price - 1.0) * 100.0

    direction_hit = (actual_return_pct >= 0 and base_return_pct >= 0) or (actual_return_pct < 0 and base_return_pct < 0)
    inside_band = min(bear_price, bull_price) <= actual <= max(bear_price, bull_price)

    return {
        "ticker": ticker,
        "horizon": horizon,
        "actual_price": round(actual, 4),
        "base_price": round(base_price, 4),
        "error_pct": round(error_pct, 2),
        "actual_return_pct": round(actual_return_pct, 2),
        "base_return_pct": round(base_return_pct, 2),
        "direction_hit": bool(direction_hit),
        "inside_bull_bear_range": bool(inside_band),
        "evaluated_at": _now_iso(),
    }


def compute_alerts(
    latest_payload: Dict[str, Any],
    previous_payload: Optional[Dict[str, Any]] = None,
) -> List[Dict[str, Any]]:
    """Generate simple forecast alerts from latest and previous payload."""
    alerts: List[Dict[str, Any]] = []
    ticker = latest_payload.get("ticker", "UNKNOWN")
    horizons = latest_payload.get("horizons", {})

    for horizon, item in horizons.items():
        summary = item.get("summary", {})
        confidence = int(summary.get("confidence", 0))
        risk = summary.get("risk", "")
        bear_pct = float(summary.get("bear_pct", 0))
        base_pct = float(summary.get("base_pct", 0))

        if confidence < 40:
            alerts.append({
                "ticker": ticker,
                "horizon": horizon,
                "level": "yellow",
                "message": f"Lav confidence ({confidence}%) for {ticker} {horizon}.",
            })
        if risk == "Høy":
            alerts.append({
                "ticker": ticker,
                "horizon": horizon,
                "level": "red",
                "message": f"Høy risiko for {ticker} {horizon}.",
            })
        if bear_pct <= -8:
            alerts.append({
                "ticker": ticker,
                "horizon": horizon,
                "level": "red",
                "message": f"Bear-scenario er svakt ({bear_pct:.1f}%) for {ticker} {horizon}.",
            })
        if base_pct >= 6 and confidence >= 60:
            alerts.append({
                "ticker": ticker,
                "horizon": horizon,
                "level": "green",
                "message": f"Sterkt base-scenario ({base_pct:.1f}%) med confidence {confidence}% for {ticker} {horizon}.",
            })

    if previous_payload:
        prev_horizons = previous_payload.get("horizons", {})
        for horizon, item in horizons.items():
            if horizon not in prev_horizons:
                continue
            c_now = int(item.get("summary", {}).get("confidence", 0))
            c_prev = int(prev_horizons[horizon].get("summary", {}).get("confidence", 0))
            if c_prev - c_now >= 15:
                alerts.append({
                    "ticker": ticker,
                    "horizon": horizon,
                    "level": "yellow",
                    "message": f"Confidence falt fra {c_prev}% til {c_now}% for {ticker} {horizon}.",
                })

    return alerts


def save_alerts(alerts: Sequence[Dict[str, Any]]) -> None:
    if not alerts:
        return
    ensure_forecast_dirs()
    with FORECAST_ALERTS.open("a", encoding="utf-8") as f:
        for alert in alerts:
            row = dict(alert)
            row["created_at"] = _now_iso()
            f.write(json.dumps(row, ensure_ascii=False) + "\n")


def load_alerts(limit: int = 100) -> List[Dict[str, Any]]:
    ensure_forecast_dirs()
    if not FORECAST_ALERTS.exists():
        return []
    rows: List[Dict[str, Any]] = []
    for line in FORECAST_ALERTS.read_text(encoding="utf-8").splitlines()[-limit:]:
        try:
            rows.append(json.loads(line))
        except Exception:
            continue
    return rows
