"""
forecast_backtest_engine.py

v18.4.2 Real Backtest Learning

Går gjennom lagrede prognoser, henter faktisk kurs etter valgt horisont
og oppdaterer lærende confidence-statistikk.

Ingen auto-trading-kobling.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Sequence, Tuple

from forecast_store import (
    evaluate_and_learn,
    load_forecast_log,
    load_learning_stats,
)


HORIZON_DAYS = {
    "1d": 1,
    "1w": 5,
    "1m": 21,
    "3m": 63,
    "6m": 126,
}


def _parse_iso(value: Any) -> Optional[datetime]:
    if not value:
        return None
    try:
        s = str(value).replace("Z", "+00:00")
        dt = datetime.fromisoformat(s)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except Exception:
        return None


def _age_days(payload: Dict[str, Any]) -> Optional[int]:
    dt = _parse_iso(payload.get("saved_at") or payload.get("generated_at"))
    if not dt:
        return None
    now = datetime.now(timezone.utc)
    return max(0, (now - dt).days)


def _is_due(payload: Dict[str, Any], horizon: str) -> bool:
    age = _age_days(payload)
    if age is None:
        return False
    return age >= HORIZON_DAYS.get(horizon, 999999)


def _extract_actual_price_from_series(prices: Sequence[float], horizon: str) -> Optional[float]:
    """Use the price at horizon offset if available, otherwise latest."""
    clean: List[float] = []
    for p in prices:
        try:
            f = float(p)
            if f > 0:
                clean.append(f)
        except Exception:
            continue

    if len(clean) < 2:
        return None

    target_index = min(HORIZON_DAYS.get(horizon, len(clean)-1), len(clean)-1)
    return clean[target_index]


def run_backtest_learning_batch(
    actual_price_lookup: Dict[str, Sequence[float]],
    *,
    limit: int = 500,
    max_evaluations: int = 100,
) -> Dict[str, Any]:
    """Evaluate due stored forecasts against actual price series.

    actual_price_lookup maps ticker -> price series starting around forecast date.
    In app UI we use currently available historical prices as a practical first version.
    """
    log = load_forecast_log(limit=limit)
    evaluated: List[Dict[str, Any]] = []
    skipped: List[Dict[str, Any]] = []
    errors: List[Dict[str, Any]] = []

    for payload in log:
        if len(evaluated) >= max_evaluations:
            break

        ticker = str(payload.get("ticker", "")).upper()
        if not ticker:
            skipped.append({"reason": "missing_ticker"})
            continue

        prices = actual_price_lookup.get(ticker)
        if not prices:
            skipped.append({"ticker": ticker, "reason": "missing_actual_prices"})
            continue

        horizons = payload.get("horizons", {})
        for horizon in list(horizons.keys()):
            if len(evaluated) >= max_evaluations:
                break

            if horizon not in HORIZON_DAYS:
                skipped.append({"ticker": ticker, "horizon": horizon, "reason": "unknown_horizon"})
                continue

            if not _is_due(payload, horizon):
                skipped.append({"ticker": ticker, "horizon": horizon, "reason": "not_due_yet"})
                continue

            actual_price = _extract_actual_price_from_series(prices, horizon)
            if actual_price is None:
                skipped.append({"ticker": ticker, "horizon": horizon, "reason": "not_enough_actual_prices"})
                continue

            try:
                evaluation = evaluate_and_learn(payload, actual_price=actual_price, horizon=horizon)
                evaluated.append(evaluation)
            except Exception as exc:
                errors.append({"ticker": ticker, "horizon": horizon, "error": str(exc)})

    stats = load_learning_stats()
    return {
        "evaluated_count": len(evaluated),
        "skipped_count": len(skipped),
        "error_count": len(errors),
        "evaluated": evaluated,
        "skipped_preview": skipped[:25],
        "errors": errors[:25],
        "learning_stats": stats,
    }


def summarize_backtest_learning(stats: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    stats = stats or load_learning_stats()
    global_stats = stats.get("global", {})
    tickers = stats.get("tickers", {})
    horizons = stats.get("horizons", {})

    best_tickers = sorted(
        tickers.items(),
        key=lambda kv: (kv[1].get("direction_accuracy", 0), -kv[1].get("avg_abs_error_pct", 999)),
        reverse=True,
    )[:10]
    worst_tickers = sorted(
        tickers.items(),
        key=lambda kv: (kv[1].get("direction_accuracy", 100), kv[1].get("avg_abs_error_pct", 0)),
    )[:10]

    return {
        "global": global_stats,
        "horizons": horizons,
        "best_tickers": [{"ticker": t, **v} for t, v in best_tickers],
        "worst_tickers": [{"ticker": t, **v} for t, v in worst_tickers],
        "ticker_count": len(tickers),
    }
