"""Bounded market-health observation collector; no trades, scores or alerts.

Free daily bar feeds are explicitly labelled as daily, not intraday quotes.
Provider failures preserve prior evidence and are reported in status.
"""
from __future__ import annotations
from datetime import datetime, timezone
from market_health_history import normalize
from market_health_ui import INDICATORS

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
            if key in ("us10y", "us30y"):
                value /= 10.0  # Yahoo ^TNX/^TYX quote yield multiplied by ten.
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
    return {"indicators": result, "composite": {"validated": False},
            "collection_status": {"at": now.isoformat(), "updated": [k for k in SYMBOLS if k in result and k not in errors],
                                  "errors": errors, "cadence": "4h poll / daily bar publication",
                                  "mode": "READ_ONLY"}}
