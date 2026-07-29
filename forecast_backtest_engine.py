"""
forecast_backtest_engine.py

v18.5.16 Date-precise Backtest Learning

Går gjennom lagrede prognoser, matcher prognosedato + horisont mot faktisk
handelsdato, og oppdaterer lærende confidence-statistikk.

Ingen auto-trading-kobling.
"""

from __future__ import annotations

from datetime import date, datetime, time, timedelta, timezone
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple

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
    if isinstance(value, datetime):
        dt = value
    elif isinstance(value, date):
        dt = datetime.combine(value, time.min)
    else:
        try:
            s = str(value).replace("Z", "+00:00")
            dt = datetime.fromisoformat(s)
        except Exception:
            return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


def _payload_datetime(payload: Mapping[str, Any]) -> Optional[datetime]:
    return _parse_iso(payload.get("generated_at") or payload.get("saved_at"))


def _age_days(payload: Dict[str, Any]) -> Optional[int]:
    dt = _payload_datetime(payload)
    if not dt:
        return None
    now = datetime.now(timezone.utc)
    return max(0, (now - dt).days)


def _is_due(payload: Dict[str, Any], horizon: str) -> bool:
    age = _age_days(payload)
    if age is None:
        return False
    return age >= HORIZON_DAYS.get(horizon, 999999)


def _add_business_days(start: date, business_days: int) -> date:
    """Add trading-day style weekdays to a date. Holidays are handled by selecting
    the next available date in the actual price series.
    """
    current = start
    added = 0
    while added < business_days:
        current += timedelta(days=1)
        if current.weekday() < 5:
            added += 1
    return current


def _date_only(value: Any) -> Optional[date]:
    dt = _parse_iso(value)
    return dt.date() if dt else None


def _to_float(value: Any) -> Optional[float]:
    try:
        f = float(value)
        return f if f > 0 else None
    except Exception:
        return None


def _normalize_actual_series(series: Any) -> List[Tuple[Optional[date], float]]:
    """Normalize yfinance DataFrames/Series, dict rows, tuple rows or float lists.

    Output is ascending by date when dates are present. Legacy float-only lists are
    kept with date=None for backward compatibility, but those are marked as not
    date-precise by the extraction step.
    """
    rows: List[Tuple[Optional[date], float]] = []

    # pandas DataFrame/Series path without importing pandas as a hard dependency.
    if hasattr(series, "index") and hasattr(series, "__len__") and not isinstance(series, (list, tuple, dict, str, bytes)):
        try:
            data = series
            if hasattr(data, "columns"):
                if "Close" in list(data.columns):
                    data = data["Close"]
                elif len(data.columns) == 1:
                    data = data.iloc[:, 0]
                else:
                    numeric = data.select_dtypes(include="number") if hasattr(data, "select_dtypes") else data
                    data = numeric.iloc[:, 0]
            if hasattr(data, "dropna"):
                data = data.dropna()
            for idx, value in zip(list(data.index), list(data)):
                f = _to_float(value)
                d = _date_only(idx)
                if f is not None:
                    rows.append((d, f))
            return sorted(rows, key=lambda x: x[0] or date.min)
        except Exception:
            rows = []

    if isinstance(series, Mapping):
        # Accept {"2024-01-02": 123.4, ...}
        for k, v in series.items():
            f = _to_float(v)
            d = _date_only(k)
            if f is not None:
                rows.append((d, f))
        return sorted(rows, key=lambda x: x[0] or date.min)

    for item in series or []:
        if isinstance(item, Mapping):
            f = _to_float(item.get("close") or item.get("Close") or item.get("price") or item.get("actual_price"))
            d = _date_only(item.get("date") or item.get("Date") or item.get("timestamp") or item.get("datetime"))
            if f is not None:
                rows.append((d, f))
        elif isinstance(item, (tuple, list)) and len(item) >= 2:
            d = _date_only(item[0])
            f = _to_float(item[1])
            if f is not None:
                rows.append((d, f))
        else:
            f = _to_float(item)
            if f is not None:
                rows.append((None, f))

    has_dates = any(d is not None for d, _ in rows)
    if has_dates:
        rows = [(d, p) for d, p in rows if d is not None]
        rows.sort(key=lambda x: x[0] or date.min)
    return rows


def _extract_actual_price_from_series(
    prices: Any,
    horizon: str,
    *,
    forecast_dt: Optional[datetime] = None,
) -> Tuple[Optional[float], Dict[str, Any]]:
    """Extract the actual price at forecast date + horizon.

    Date-aware series:
    - target_date = forecast_date + horizon in business days
    - actual_date = first available trading date on/after target_date

    Float-only legacy series:
    - falls back to horizon index and marks date_precision=False
    """
    clean = _normalize_actual_series(prices)
    meta: Dict[str, Any] = {"date_precision": False}
    if len(clean) < 2:
        meta["reason"] = "not_enough_actual_prices"
        return None, meta

    horizon_days = HORIZON_DAYS.get(horizon)
    if horizon_days is None:
        meta["reason"] = "unknown_horizon"
        return None, meta

    dated = [(d, p) for d, p in clean if d is not None]
    if dated and forecast_dt is not None:
        forecast_date = forecast_dt.date()
        target_date = _add_business_days(forecast_date, horizon_days)
        last_date = dated[-1][0]
        meta.update({
            "date_precision": True,
            "forecast_date": forecast_date.isoformat(),
            "target_date": target_date.isoformat(),
            "last_actual_date": last_date.isoformat() if last_date else None,
        })

        for d, price in dated:
            if d and d >= target_date:
                meta["actual_date"] = d.isoformat()
                meta["actual_price_source"] = "target_date_or_next_trading_day"
                return price, meta

        meta["reason"] = "not_due_yet"
        return None, meta

    # Legacy fallback for old tests or manually provided price lists.
    values = [p for _, p in clean]
    target_index = min(horizon_days, len(values) - 1)
    meta.update({
        "actual_index": target_index,
        "actual_price_source": "legacy_horizon_index",
        "reason": "legacy_price_series_without_dates",
    })
    return values[target_index], meta


def run_backtest_learning_batch(
    actual_price_lookup: Dict[str, Any],
    *,
    limit: int = 500,
    max_evaluations: int = 100,
) -> Dict[str, Any]:
    """Evaluate due stored forecasts against actual price series.

    actual_price_lookup maps ticker -> dated price series. The preferred shape is
    a yfinance DataFrame/Series, a list of {date, close}, or (date, close) pairs.
    Float-only lists still work as a legacy fallback but are not marked
    date-precise.
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
        if prices is None or prices == []:
            skipped.append({"ticker": ticker, "reason": "missing_actual_prices"})
            continue

        forecast_dt = _payload_datetime(payload)
        horizons = payload.get("horizons", {})
        for horizon in list(horizons.keys()):
            if len(evaluated) >= max_evaluations:
                break

            if horizon not in HORIZON_DAYS:
                skipped.append({"ticker": ticker, "horizon": horizon, "reason": "unknown_horizon"})
                continue

            actual_price, meta = _extract_actual_price_from_series(prices, horizon, forecast_dt=forecast_dt)

            # For legacy float-only series, keep the old due check. For dated
            # series, the extractor itself decides if the target date has a real
            # actual price available.
            if not meta.get("date_precision") and not _is_due(payload, horizon):
                skipped.append({"ticker": ticker, "horizon": horizon, "reason": "not_due_yet", **meta})
                continue

            if actual_price is None:
                skipped.append({"ticker": ticker, "horizon": horizon, **meta})
                continue

            try:
                evaluation = evaluate_and_learn(
                    payload,
                    actual_price=actual_price,
                    horizon=horizon,
                    forecast_date=meta.get("forecast_date"),
                    target_date=meta.get("target_date"),
                    actual_date=meta.get("actual_date"),
                    date_precision=bool(meta.get("date_precision")),
                )
                evaluation.update({k: v for k, v in meta.items() if k not in evaluation})
                evaluated.append(evaluation)
            except Exception as exc:
                errors.append({"ticker": ticker, "horizon": horizon, "error": str(exc), **meta})

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
