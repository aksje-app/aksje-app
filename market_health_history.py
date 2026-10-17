"""Pure market-health observation normalization and historical changes.

Read-only functions: ingestion workers may reuse these; no network access,
trade writes or invented source values.
"""
from __future__ import annotations
from datetime import datetime, timezone, timedelta
from math import isfinite
from market_health_ui import INDICATORS

WINDOWS = {"24t": timedelta(days=1), "7d": timedelta(days=7), "30d": timedelta(days=30)}
MAX_FUTURE_SECONDS = 60
MAX_AGE = {"cape": timedelta(days=45), "equity_yield": timedelta(days=45),
           "credit": timedelta(days=5), "breadth": timedelta(days=2),
           **{key: timedelta(hours=36) for key in INDICATORS if key not in
              ("cape", "equity_yield", "credit", "breadth")}}


def _parse_time(value):
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        return parsed.astimezone(timezone.utc) if parsed.tzinfo else None
    except (TypeError, ValueError, OverflowError):
        return None


def normalize(key, row, *, now=None):
    if key not in INDICATORS or not isinstance(row, dict):
        return None
    at = _parse_time(row.get("observed_at"))
    now = now or datetime.now(timezone.utc)
    try:
        value = float(row.get("value"))
    except (ValueError, TypeError):
        return None
    source = str(row.get("source") or "").strip()
    if not at or not source or not isfinite(value) or at > now + timedelta(seconds=MAX_FUTURE_SECONDS):
        return None
    # Daily bars remain the latest valid session close during weekends.
    age = now - at
    if (key not in ("cape", "equity_yield", "credit", "breadth")
            and now.weekday() in (5, 6)
            and at.weekday() == 4
            and 0 <= (now.date() - at.date()).days <= 2):
        # Only the immediately preceding Friday gets a weekend allowance.
        age = min(age, timedelta(hours=24))
    return {"value": value, "observed_at": at.isoformat(), "source": source,
            "status": "STALE" if age > MAX_AGE[key] else "CURRENT"}


def summarize(key, history, *, now=None):
    """Select closest observation at/before each cutoff, never extrapolate."""
    now = now or datetime.now(timezone.utc)
    valid = [v for raw in history if (v := normalize(key, raw, now=now))]
    valid.sort(key=lambda x: x["observed_at"])
    latest = valid[-1] if valid else None
    output = {"latest": latest, "history": {}, "count": len(valid)}
    if not latest:
        return output
    for window, duration in WINDOWS.items():
        cutoff = _parse_time(latest["observed_at"]) - duration
        prior = [x for x in valid if _parse_time(x["observed_at"]) <= cutoff]
        if not prior:
            output["history"][window] = {"status": "INSUFFICIENT_HISTORY"}
            continue
        baseline = prior[-1]
        difference = latest["value"] - baseline["value"]
        output["history"][window] = {
            "status": "MEASURED", "difference": round(difference, 5),
            "pct_change": round(difference / abs(baseline["value"]) * 100, 5) if baseline["value"] else None,
            "baseline_at": baseline["observed_at"], "latest_at": latest["observed_at"],
        }
    return output
