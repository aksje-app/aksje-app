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


def get_forecast_vs_actual_series(
    forecast_payload: Dict[str, Any],
    actual_prices: Sequence[float],
    horizon: str,
) -> Dict[str, Any]:
    """Build aligned forecast-vs-actual series for charting.

    Returns a dict with:
    - labels
    - actual
    - base
    - bull
    - bear
    - lower_band
    - upper_band
    - evaluation if actual has terminal price
    """
    horizons = forecast_payload.get("horizons", {})
    item = horizons.get(horizon)
    if not item:
        raise ValueError(f"Mangler horisont i forecast payload: {horizon}")

    points = item.get("points", [])
    if not points:
        raise ValueError("Forecast mangler punkter.")

    clean_actual: List[float] = []
    for value in actual_prices:
        try:
            f = float(value)
            if f > 0:
                clean_actual.append(f)
        except Exception:
            continue

    max_len = min(len(points), len(clean_actual)) if clean_actual else len(points)
    labels = [p.get("date_label", str(i)) for i, p in enumerate(points[:max_len])]

    result = {
        "ticker": forecast_payload.get("ticker", "UNKNOWN"),
        "horizon": horizon,
        "labels": labels,
        "actual": clean_actual[:max_len] if clean_actual else [],
        "base": [p.get("base") for p in points[:max_len]],
        "bull": [p.get("bull") for p in points[:max_len]],
        "bear": [p.get("bear") for p in points[:max_len]],
        "lower_band": [p.get("lower_band") for p in points[:max_len]],
        "upper_band": [p.get("upper_band") for p in points[:max_len]],
        "evaluation": None,
    }

    if clean_actual and len(clean_actual) >= 2:
        result["evaluation"] = evaluate_forecast_accuracy(
            forecast_payload,
            actual_price=clean_actual[min(len(clean_actual), len(points)) - 1],
            horizon=horizon,
        )

    return result


def _alert_priority(level: str) -> int:
    level = (level or "").lower()
    if level == "red":
        return 3
    if level == "yellow":
        return 2
    if level == "green":
        return 1
    return 0


def _dedupe_alerts(alerts: Sequence[Dict[str, Any]]) -> List[Dict[str, Any]]:
    seen = set()
    result: List[Dict[str, Any]] = []
    for alert in alerts:
        key = (
            alert.get("ticker"),
            alert.get("horizon"),
            alert.get("level"),
            alert.get("message"),
        )
        if key in seen:
            continue
        seen.add(key)
        result.append(dict(alert))
    result.sort(key=lambda a: _alert_priority(a.get("level", "")), reverse=True)
    return result


def compute_intelligent_alerts(
    latest_payload: Dict[str, Any],
    previous_payload: Optional[Dict[str, Any]] = None,
) -> List[Dict[str, Any]]:
    """More advanced forecast alerts.

    Focus:
    - confidence collapse
    - strength collapse / improvement
    - bear risk expansion
    - strong opportunity
    - high-risk false-positive protection
    """
    alerts: List[Dict[str, Any]] = []
    ticker = latest_payload.get("ticker", "UNKNOWN")
    horizons = latest_payload.get("horizons", {})
    prev_horizons = (previous_payload or {}).get("horizons", {}) if previous_payload else {}

    for horizon, item in horizons.items():
        summary = item.get("summary", {})
        confidence = int(summary.get("confidence", 0))
        strength = int(summary.get("forecast_strength", 0))
        strength_label = summary.get("forecast_strength_label", "")
        risk = summary.get("risk", "")
        base_pct = float(summary.get("base_pct", 0))
        bull_pct = float(summary.get("bull_pct", 0))
        bear_pct = float(summary.get("bear_pct", 0))
        volatility = float(summary.get("volatility_annual", 0))

        # Red warnings
        if strength < 35 and confidence < 50:
            alerts.append({
                "ticker": ticker,
                "horizon": horizon,
                "level": "red",
                "category": "weak_forecast",
                "message": f"Svak prognose: Strength {strength}/100 og confidence {confidence}% for {ticker} {horizon}.",
            })

        if bear_pct <= -10 and risk == "Høy":
            alerts.append({
                "ticker": ticker,
                "horizon": horizon,
                "level": "red",
                "category": "bear_risk",
                "message": f"Økt bear-risiko: bear-scenario {bear_pct:.1f}% og høy risiko for {ticker} {horizon}.",
            })

        if volatility >= 0.70:
            alerts.append({
                "ticker": ticker,
                "horizon": horizon,
                "level": "red",
                "category": "volatility",
                "message": f"Svært høy volatilitet ({volatility:.0%}) gjør prognosen usikker for {ticker} {horizon}.",
            })

        # Yellow warnings
        if confidence < 45 and strength >= 55:
            alerts.append({
                "ticker": ticker,
                "horizon": horizon,
                "level": "yellow",
                "category": "low_confidence",
                "message": f"Mulig mulighet, men lav confidence ({confidence}%) for {ticker} {horizon}.",
            })

        if base_pct > 0 and bear_pct < -7:
            alerts.append({
                "ticker": ticker,
                "horizon": horizon,
                "level": "yellow",
                "category": "asymmetric_risk",
                "message": f"Asymmetrisk risiko: base {base_pct:+.1f}% men bear {bear_pct:.1f}% for {ticker} {horizon}.",
            })

        # Green opportunity alerts
        if strength >= 75 and confidence >= 60 and risk != "Høy" and base_pct > 2:
            alerts.append({
                "ticker": ticker,
                "horizon": horizon,
                "level": "green",
                "category": "strong_opportunity",
                "message": f"Sterkt scenario: Strength {strength}/100, base {base_pct:+.1f}%, confidence {confidence}% for {ticker} {horizon}.",
            })

        if bull_pct >= 12 and bear_pct > -8 and confidence >= 55:
            alerts.append({
                "ticker": ticker,
                "horizon": horizon,
                "level": "green",
                "category": "good_reward_risk",
                "message": f"God reward/risk: bull {bull_pct:+.1f}% og bear {bear_pct:.1f}% for {ticker} {horizon}.",
            })

        # Change alerts vs previous forecast
        prev = prev_horizons.get(horizon, {}).get("summary", {})
        if prev:
            prev_conf = int(prev.get("confidence", confidence))
            prev_strength = int(prev.get("forecast_strength", strength))
            prev_bear = float(prev.get("bear_pct", bear_pct))
            prev_base = float(prev.get("base_pct", base_pct))

            if prev_strength - strength >= 15:
                alerts.append({
                    "ticker": ticker,
                    "horizon": horizon,
                    "level": "yellow",
                    "category": "strength_drop",
                    "message": f"Strength falt fra {prev_strength} til {strength} for {ticker} {horizon}.",
                })

            if strength - prev_strength >= 15:
                alerts.append({
                    "ticker": ticker,
                    "horizon": horizon,
                    "level": "green",
                    "category": "strength_improved",
                    "message": f"Strength økte fra {prev_strength} til {strength} for {ticker} {horizon}.",
                })

            if prev_conf - confidence >= 15:
                alerts.append({
                    "ticker": ticker,
                    "horizon": horizon,
                    "level": "yellow",
                    "category": "confidence_drop",
                    "message": f"Confidence falt fra {prev_conf}% til {confidence}% for {ticker} {horizon}.",
                })

            if bear_pct - prev_bear <= -5:
                alerts.append({
                    "ticker": ticker,
                    "horizon": horizon,
                    "level": "red",
                    "category": "bear_worsened",
                    "message": f"Bear-scenario ble svakere fra {prev_bear:+.1f}% til {bear_pct:+.1f}% for {ticker} {horizon}.",
                })

            if base_pct - prev_base >= 5 and strength >= 60:
                alerts.append({
                    "ticker": ticker,
                    "horizon": horizon,
                    "level": "green",
                    "category": "base_improved",
                    "message": f"Base-scenario forbedret fra {prev_base:+.1f}% til {base_pct:+.1f}% for {ticker} {horizon}.",
                })

    return _dedupe_alerts(alerts)


def summarize_alerts(alerts: Sequence[Dict[str, Any]]) -> Dict[str, Any]:
    """Summarize alerts for dashboard/UI."""
    counts = {"red": 0, "yellow": 0, "green": 0}
    categories: Dict[str, int] = {}
    for alert in alerts:
        level = (alert.get("level") or "").lower()
        if level in counts:
            counts[level] += 1
        cat = alert.get("category") or "other"
        categories[cat] = categories.get(cat, 0) + 1
    top_level = "green"
    if counts["red"]:
        top_level = "red"
    elif counts["yellow"]:
        top_level = "yellow"
    return {
        "counts": counts,
        "categories": categories,
        "top_level": top_level,
        "total": len(alerts),
    }
