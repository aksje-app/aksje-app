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

from forecast_engine import build_all_horizons, SUPPORTED_HORIZONS


DATA_DIR = Path("data")
FORECAST_DIR = DATA_DIR / "forecasts"
FORECAST_LOG = FORECAST_DIR / "forecast_log.jsonl"
FORECAST_ALERTS = FORECAST_DIR / "forecast_alerts.jsonl"


def _service_storage():
    try:
        from services.storage_service import get_storage_service

        return get_storage_service()
    except Exception:
        return None


def _storage_name(name: str) -> str:
    return f"forecasts/{name}"


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

    storage = _service_storage()
    if storage is not None:
        try:
            storage.write_json(_storage_name(f"{ticker_safe}_latest.json"), payload)
            storage.append_jsonl(_storage_name("forecast_log.jsonl"), payload)
        except Exception:
            pass

    latest_path = FORECAST_DIR / f"{ticker_safe}_latest.json"
    latest_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    with FORECAST_LOG.open("a", encoding="utf-8") as f:
        f.write(json.dumps(payload, ensure_ascii=False) + "\n")

    return latest_path


def load_latest_forecast(ticker: str) -> Optional[Dict[str, Any]]:
    ensure_forecast_dirs()
    ticker_safe = _safe_ticker(ticker)
    storage = _service_storage()
    if storage is not None:
        try:
            stored = storage.read_json(_storage_name(f"{ticker_safe}_latest.json"), default=None)
            if isinstance(stored, dict):
                return stored
        except Exception:
            pass

    path = FORECAST_DIR / f"{ticker_safe}_latest.json"
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


def load_forecast_log(limit: int = 200) -> List[Dict[str, Any]]:
    ensure_forecast_dirs()
    storage = _service_storage()
    if storage is not None:
        try:
            stored_rows = storage.read_jsonl(_storage_name("forecast_log.jsonl"), limit=limit)
            if stored_rows:
                return stored_rows
        except Exception:
            pass

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
    market_regime: str = "neutral",
    event_risk: bool = False,
    learned_confidence_adjustment: int = 0,
) -> Dict[str, Any]:
    """Build all horizon forecasts and persist them."""
    result = build_all_horizons(
        ticker,
        prices,
        ai_score=ai_score,
        sentiment_score=sentiment_score,
        market_regime=market_regime,
        event_risk=event_risk,
        learned_confidence_adjustment=learned_confidence_adjustment,
    )
    payload = {
        "ticker": ticker.upper(),
        "generated_at": _now_iso(),
        "ai_score": ai_score,
        "sentiment_score": sentiment_score,
        "market_regime": market_regime,
        "event_risk": bool(event_risk),
        "learned_confidence_adjustment": int(learned_confidence_adjustment or 0),
        "horizons": result,
    }
    save_forecast_result(ticker, payload)
    return payload


def evaluate_forecast_accuracy(
    forecast_payload: Dict[str, Any],
    actual_price: float,
    horizon: str,
    *,
    forecast_date: Optional[str] = None,
    target_date: Optional[str] = None,
    actual_date: Optional[str] = None,
    date_precision: bool = False,
) -> Dict[str, Any]:
    """Compare forecast against an actual price for one horizon.

    v18.5.16 adds optional date metadata so learning can document exactly
    which forecast date, target date and actual trading date were evaluated.
    """
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

    evaluation = {
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
        "date_precision": bool(date_precision),
    }
    if forecast_date:
        evaluation["forecast_date"] = forecast_date
    if target_date:
        evaluation["target_date"] = target_date
    if actual_date:
        evaluation["actual_date"] = actual_date
    return evaluation


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
    storage = _service_storage()
    with FORECAST_ALERTS.open("a", encoding="utf-8") as f:
        for alert in alerts:
            row = dict(alert)
            row["created_at"] = _now_iso()
            if storage is not None:
                try:
                    storage.append_jsonl(_storage_name("forecast_alerts.jsonl"), row)
                except Exception:
                    pass
            f.write(json.dumps(row, ensure_ascii=False) + "\n")


def load_alerts(limit: int = 100) -> List[Dict[str, Any]]:
    ensure_forecast_dirs()
    storage = _service_storage()
    if storage is not None:
        try:
            stored_rows = storage.read_jsonl(_storage_name("forecast_alerts.jsonl"), limit=limit)
            if stored_rows:
                return stored_rows
        except Exception:
            pass

    if not FORECAST_ALERTS.exists():
        return []
    rows: List[Dict[str, Any]] = []
    for line in FORECAST_ALERTS.read_text(encoding="utf-8").splitlines()[-limit:]:
        try:
            rows.append(json.loads(line))
        except Exception:
            continue
    return rows


def _forecast_age_days(payload: Dict[str, Any]) -> Optional[int]:
    raw = payload.get("saved_at") or payload.get("generated_at")
    if not raw:
        return None
    try:
        dt = datetime.fromisoformat(str(raw).replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return max(0, (datetime.now(timezone.utc) - dt).days)
    except Exception:
        return None


def get_forecast_vs_actual_series(
    forecast_payload: Dict[str, Any],
    actual_prices: Sequence[float],
    horizon: str,
) -> Dict[str, Any]:
    """Build forecast-vs-actual series with a clean time split.

    The previous version aligned historical actual prices directly onto future
    forecast labels. This made the green actual-price line continue into the
    future. v18.5.15 separates:
    - historical actual prices before today
    - today/current price
    - future forecast points only after today
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

    today_label = str(points[0].get("date_label") or "I dag")
    history_window = min(max(len(clean_actual) - 1, 0), 60)
    history_values = clean_actual[-(history_window + 1):] if clean_actual else []
    history_labels = [f"T-{i}" for i in range(history_window, 0, -1)]

    future_points = list(points[1:])
    future_labels = [str(p.get("date_label", f"+{idx}")) for idx, p in enumerate(future_points, start=1)]
    labels = history_labels + [today_label] + future_labels

    def projected(field: str) -> List[Any]:
        return [None] * history_window + [p.get(field) for p in points]

    actual_series: List[Any] = []
    if history_values:
        actual_series = history_values + [None] * len(future_points)

    result = {
        "ticker": forecast_payload.get("ticker", "UNKNOWN"),
        "horizon": horizon,
        "labels": labels,
        "today_label": today_label,
        "today_index": history_window,
        "future_start_index": history_window + 1,
        "actual": actual_series,
        "base": projected("base"),
        "bull": projected("bull"),
        "bear": projected("bear"),
        "lower_band": projected("lower_band"),
        "upper_band": projected("upper_band"),
        "evaluation": None,
    }

    age = _forecast_age_days(forecast_payload)
    horizon_days = int(SUPPORTED_HORIZONS.get(horizon, 999999))
    if clean_actual and age is not None and age >= horizon_days:
        result["evaluation"] = evaluate_forecast_accuracy(
            forecast_payload,
            actual_price=clean_actual[-1],
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


LEARNING_STATS = FORECAST_DIR / "forecast_learning_stats.json"


def load_learning_stats() -> Dict[str, Any]:
    """Load learned confidence stats."""
    ensure_forecast_dirs()
    empty = {"global": {}, "tickers": {}, "horizons": {}}
    storage = _service_storage()
    if storage is not None:
        try:
            stored = storage.read_json(_storage_name("forecast_learning_stats.json"), default=None)
            if isinstance(stored, dict):
                stored.setdefault("global", {})
                stored.setdefault("tickers", {})
                stored.setdefault("horizons", {})
                return stored
        except Exception:
            pass

    if not LEARNING_STATS.exists():
        return empty
    try:
        data = json.loads(LEARNING_STATS.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            return empty
        data.setdefault("global", {})
        data.setdefault("tickers", {})
        data.setdefault("horizons", {})
        return data
    except Exception:
        return empty


def save_learning_stats(stats: Dict[str, Any]) -> None:
    ensure_forecast_dirs()
    storage = _service_storage()
    if storage is not None:
        try:
            storage.write_json(_storage_name("forecast_learning_stats.json"), stats)
        except Exception:
            pass
    LEARNING_STATS.write_text(json.dumps(stats, ensure_ascii=False, indent=2), encoding="utf-8")


def _update_bucket(bucket: Dict[str, Any], evaluation: Dict[str, Any]) -> Dict[str, Any]:
    count = int(bucket.get("count", 0)) + 1
    direction_hits = int(bucket.get("direction_hits", 0)) + (1 if evaluation.get("direction_hit") else 0)
    inside_band_hits = int(bucket.get("inside_band_hits", 0)) + (1 if evaluation.get("inside_bull_bear_range") else 0)
    abs_error_sum = float(bucket.get("abs_error_sum", 0.0)) + abs(float(evaluation.get("error_pct", 0.0)))

    bucket["count"] = count
    bucket["direction_hits"] = direction_hits
    bucket["inside_band_hits"] = inside_band_hits
    bucket["abs_error_sum"] = round(abs_error_sum, 4)
    bucket["direction_accuracy"] = round(direction_hits / count * 100.0, 2)
    bucket["inside_band_accuracy"] = round(inside_band_hits / count * 100.0, 2)
    bucket["avg_abs_error_pct"] = round(abs_error_sum / count, 2)
    bucket["updated_at"] = _now_iso()
    return bucket


def update_learning_from_evaluation(evaluation: Dict[str, Any]) -> Dict[str, Any]:
    """Update learning stats from one forecast evaluation."""
    stats = load_learning_stats()
    ticker = str(evaluation.get("ticker", "UNKNOWN")).upper()
    horizon = str(evaluation.get("horizon", "unknown"))

    stats["global"] = _update_bucket(stats.get("global", {}), evaluation)

    tickers = stats.setdefault("tickers", {})
    tickers[ticker] = _update_bucket(tickers.get(ticker, {}), evaluation)

    horizons = stats.setdefault("horizons", {})
    horizons[horizon] = _update_bucket(horizons.get(horizon, {}), evaluation)

    save_learning_stats(stats)
    return stats


def learning_confidence_adjustment(
    *,
    ticker: str,
    horizon: str,
    base_confidence: int,
    stats: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Return adjusted confidence based on learned historical accuracy.

    Conservative rule:
    - Needs at least 5 samples before strong adjustment.
    - Direction accuracy and avg error influence confidence.
    - Adjustment capped to +/- 15 points.
    """
    stats = stats or load_learning_stats()
    ticker = (ticker or "UNKNOWN").upper()
    horizon = horizon or "unknown"

    buckets = []
    for bucket in [
        stats.get("global", {}),
        stats.get("horizons", {}).get(horizon, {}),
        stats.get("tickers", {}).get(ticker, {}),
    ]:
        if bucket and int(bucket.get("count", 0)) > 0:
            buckets.append(bucket)

    if not buckets:
        return {
            "base_confidence": int(base_confidence),
            "adjusted_confidence": int(base_confidence),
            "adjustment": 0,
            "reason": "Ingen læringshistorikk ennå.",
            "samples": 0,
        }

    total_weight = 0.0
    score_sum = 0.0
    samples = 0

    for bucket in buckets:
        count = int(bucket.get("count", 0))
        samples += count
        weight = min(count / 10.0, 1.0)
        direction_acc = float(bucket.get("direction_accuracy", 50.0))
        inside_acc = float(bucket.get("inside_band_accuracy", 50.0))
        avg_error = float(bucket.get("avg_abs_error_pct", 8.0))

        # 50 is neutral. Above 60 improves, below 45 weakens.
        quality = (direction_acc - 50.0) * 0.45 + (inside_acc - 50.0) * 0.25 - max(0.0, avg_error - 6.0) * 1.2
        score_sum += quality * weight
        total_weight += weight

    if total_weight <= 0:
        adjustment = 0
    else:
        raw_adjustment = score_sum / total_weight / 3.0
        adjustment = int(round(max(-15.0, min(15.0, raw_adjustment))))

    # Extra conservative if very few samples
    if samples < 5:
        adjustment = int(round(adjustment * 0.35))
        reason = "Lite læringshistorikk, bruker svak justering."
    elif samples < 15:
        adjustment = int(round(adjustment * 0.65))
        reason = "Moderat læringshistorikk, bruker forsiktig justering."
    else:
        reason = "Læringshistorikk brukt til confidence-justering."

    adjusted = int(max(5, min(95, int(base_confidence) + adjustment)))

    return {
        "base_confidence": int(base_confidence),
        "adjusted_confidence": adjusted,
        "adjustment": adjustment,
        "reason": reason,
        "samples": samples,
    }


def evaluate_and_learn(
    forecast_payload: Dict[str, Any],
    actual_price: float,
    horizon: str,
    *,
    forecast_date: Optional[str] = None,
    target_date: Optional[str] = None,
    actual_date: Optional[str] = None,
    date_precision: bool = False,
) -> Dict[str, Any]:
    """Evaluate a forecast and update learning stats in one step."""
    evaluation = evaluate_forecast_accuracy(
        forecast_payload,
        actual_price=actual_price,
        horizon=horizon,
        forecast_date=forecast_date,
        target_date=target_date,
        actual_date=actual_date,
        date_precision=date_precision,
    )
    stats = update_learning_from_evaluation(evaluation)
    evaluation["learning_stats_updated"] = True
    evaluation["learning_stats"] = {
        "global": stats.get("global", {}),
        "ticker": stats.get("tickers", {}).get(evaluation.get("ticker", ""), {}),
        "horizon": stats.get("horizons", {}).get(horizon, {}),
    }
    return evaluation
