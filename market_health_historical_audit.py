"""Read-only historical coverage audit for the 14-indicator composite.

Observation counts alone are insufficient: dates, spacing and point-in-time
availability must be independently validated before fitting weights.
"""
from datetime import datetime, timezone
from market_health_ui import INDICATORS

MIN_YEARS = 10

def coverage_report(snapshot):
    rows = (snapshot or {}).get("indicators", {})
    rows = rows if isinstance(rows, dict) else {}
    report = {}
    for key in INDICATORS:
        datum = rows.get(key, {})
        observations = datum.get("observations", []) if isinstance(datum, dict) else []
        dated = set()
        for row in observations:
            if not isinstance(row, dict):
                continue
            try:
                at = datetime.fromisoformat(str(row["observed_at"]).replace("Z", "+00:00"))
                val = float(row["value"])
                from math import isfinite
                if at.tzinfo and isfinite(val) and row.get("source"):
                    dated.add(at.astimezone(timezone.utc).date())
            except (KeyError, ValueError, TypeError, OverflowError):
                pass
        dates = sorted(dated)
        years = (dates[-1] - dates[0]).days / 365.25 if len(dates) > 1 else 0.0
        report[key] = {
            "dated_observations": len(dates),
            "first": dates[0].isoformat() if dates else None,
            "last": dates[-1].isoformat() if dates else None,
            "span_years": round(years, 2),
            "minimum_span_met": years >= MIN_YEARS,
            "historical_coverage_verified": False,
            "reason": "Point-in-time constituents, sampling, publication lags and gaps still require audit.",
        }
    return {
        "mode": "READ_ONLY",
        "minimum_target_years": MIN_YEARS,
        "indicators": report,
        "all_spans_met": all(x["minimum_span_met"] for x in report.values()),
        "validated": False,
        "calibration_approved": False,
        "trade_signals_enabled": False,
    }
