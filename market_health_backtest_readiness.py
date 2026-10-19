"""Historical, read-only composite feasibility audit without look-ahead.

This is NOT predictive validation. Prices and macro series can be revised;
point-in-time publication times and out-of-sample outcomes remain mandatory.
"""
from datetime import datetime, timezone
from math import isfinite

CORE = ("vix","trend","curve","us10y","us30y")
MIN_YEARS = 10

def assess_historical_feasibility(snapshot):
    indicators=(snapshot or {}).get("indicators") or {}
    evidence={}
    for key in CORE:
        series={}
        for row in (indicators.get(key) or {}).get("observations") or []:
            try:
                dt=datetime.fromisoformat(str(row["observed_at"]).replace("Z","+00:00"))
                value=float(row["value"])
                if dt.tzinfo is not None and isfinite(value) and row.get("source"):
                    series[dt.astimezone(timezone.utc).date()]=value
            except (KeyError,TypeError,ValueError,OverflowError):
                continue
        dates=sorted(series)
        span=(dates[-1]-dates[0]).days/365.25 if len(dates)>1 else 0
        evidence[key]={"count":len(dates),"span_years":round(span,2),
                       "span_ok":span>=MIN_YEARS and len(dates)>=2000}
    return {"mode":"READ_ONLY","historical_coverage":evidence,
            "coverage_ready":all(x["span_ok"] for x in evidence.values()),
            "point_in_time_verified":False,"walk_forward_tested":False,
            "out_of_sample_verified":False,"validated":False,
            "trade_signals_enabled":False}
