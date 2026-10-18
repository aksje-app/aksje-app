"""Bounded market-health observation collector; no trades, scores or alerts.

Free daily bar feeds are explicitly labelled as daily, not intraday quotes.
Provider failures preserve prior evidence and are reported in status.
"""
from __future__ import annotations
from datetime import datetime, timezone, timedelta
from urllib.request import urlopen
from csv import DictReader
from io import StringIO
from math import isfinite
from market_health_history import normalize
from market_health_ui import INDICATORS

FRED_SERIES = {"curve": "T10Y2Y", "credit": "BAMLH0A0HYM2"}


def fred_daily(series_id):
    """Public FRED CSV daily history; use date at UTC midnight, no invented quote time."""
    url = "https://fred.stlouisfed.org/graph/fredgraph.csv?id=" + series_id
    with urlopen(url, timeout=12) as response:
        payload = response.read(600000).decode("utf-8-sig")
    observations = []
    for row in DictReader(StringIO(payload)):
        raw = str(row.get(series_id) or "").strip()
        date = row.get("DATE") or row.get("observation_date")
        try:
            value = float(raw)
            at = datetime.fromisoformat(str(date)).replace(tzinfo=timezone.utc)
            if isfinite(value):
                observations.append({"value": value, "source": f"FRED daily series {series_id}", "observed_at": at.isoformat()})
        except (ValueError, TypeError):
            continue
    if not observations:
        raise ValueError("FRED series has no valid observations")
    return observations[-96:]


SYMBOLS = {"vix": "^VIX", "us10y": "^TNX", "us30y": "^TYX",
           "brent": "BZ=F", "gold": "GC=F", "dxy": "DX-Y.NYB",
           "eurusd": "EURUSD=X", "trend": "^GSPC"}


def collect(snapshot=None, *, history_provider=None, now=None):
    now = now or datetime.now(timezone.utc)
    saved = dict(snapshot or {})
    previous = saved.get("indicators") or {}
    previous = previous if isinstance(previous, dict) else {}
    result = dict(previous)
    errors = {}
    if history_provider is None:
        import yfinance as yf
        history_provider = lambda symbol: yf.Ticker(symbol).history(period="1y" if symbol == "^GSPC" else "35d", interval="1d", auto_adjust=False)
    for key, symbol in SYMBOLS.items():
        try:
            frame = history_provider(symbol)
            if frame is None or frame.empty:
                raise ValueError("empty daily price history")
            if "Close" not in frame:
                raise ValueError("missing Close")
            series = frame["Close"].dropna()
            if series.empty:
                raise ValueError("no finite closing price")
            last_time = series.index[-1]
            if getattr(last_time, "tzinfo", None) is None:
                raise ValueError("unqualified timestamp")
            observed = last_time.to_pydatetime().astimezone(timezone.utc)
            value = float(series.iloc[-1])
            # Yahoo ^TNX/^TYX responses observed in production are already percent yields.
            # Do not divide a percent yield by ten without an independently verified unit contract.
            if key == "trend":
                if len(series) < 200:
                    raise ValueError("200-day baseline unavailable")
                avg = float(series.iloc[-200:].mean())
                if avg <= 0:
                    raise ValueError("invalid 200-day baseline")
                value = (value / avg - 1.0) * 100.0
            row = {"value": value, "source": f"Yahoo Finance daily observation ({symbol})",
                   "observed_at": observed.isoformat()}
            checked = normalize(key, row, now=now)
            if not checked:
                raise ValueError("invalid dated observation")
            old = result.get(key) or {}
            observations = list(old.get("observations") or []) if isinstance(old, dict) else []
            if not any(o.get("observed_at") == row["observed_at"] for o in observations if isinstance(o, dict)):
                observations.append(row)
            observations = sorted((x for x in observations if isinstance(x,dict) and x.get("observed_at")),key=lambda x:x["observed_at"])[-96:]
            result[key] = {**row,"observations":observations}
        except Exception as exc:
            errors[key] = str(exc)[:180]
    for key, series_id in FRED_SERIES.items():
        try:
            records = fred_daily(series_id)
            row = records[-1]
            if not normalize(key, row, now=now):
                raise ValueError("invalid FRED date/source")
            old = result.get(key) or {}
            combined = list(old.get("observations") or []) if isinstance(old, dict) else []
            unique = {r["observed_at"]: r for r in combined + records if isinstance(r, dict) and r.get("observed_at")}
            result[key] = {**row, "observations": sorted(unique.values(), key=lambda r: r["observed_at"])[-96:]}
        except Exception as exc:
            errors[key] = str(exc)[:180]
    return {"indicators": result, "composite": {"validated": False},
            "collection_status": {"at": now.isoformat(), "updated": [k for k in (*SYMBOLS, *FRED_SERIES) if k in result and k not in errors],
                                  "errors": errors, "cadence": "4h poll / daily bar publication",
                                  "mode": "READ_ONLY"}}
