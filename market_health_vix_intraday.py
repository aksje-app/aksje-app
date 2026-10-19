"""VIX intraday overlay: observed timestamps only, no trades or fabricated prices."""
from datetime import datetime, timedelta, timezone, time
from zoneinfo import ZoneInfo
from math import isfinite

NY=ZoneInfo("America/New_York")
def us_regular_session(now):
    ny=now.astimezone(NY)
    return ny.weekday()<5 and time(9,30)<=ny.time()<time(16,0)

def update_vix_intraday(snapshot, *, now=None, provider=None):
    now=now or datetime.now(timezone.utc)
    result=dict(snapshot or {})
    state=dict(result.get("vix_intraday_status") or {})
    if not us_regular_session(now):
        # Outside the session, revert to last daily close, never label prior intraday live.
        indicators=dict(result.get("indicators") or {})
        vix=dict(indicators.get("vix") or {})
        if vix.get("source_kind")=="INTRADAY":
            rows=vix.get("observations") or []
            if rows:
                latest=max(rows,key=lambda r:r["observed_at"])
                indicators["vix"]={**latest,"observations":rows}
                result["indicators"]=indicators
        state["state"]="MARKET_CLOSED"
        result["vix_intraday_status"]=state
        return result
    try:
        last=datetime.fromisoformat(str(state.get("attempt_at")).replace("Z","+00:00"))
        if last.tzinfo and now-last<timedelta(minutes=30):
            return result
    except (TypeError,ValueError):
        pass
    state["attempt_at"]=now.isoformat()
    try:
        if provider is None:
            import yfinance as yf
            provider=lambda: yf.Ticker("^VIX").history(period="1d",interval="5m",auto_adjust=False)
        frame=provider()
        if frame is None or frame.empty or "Close" not in frame:
            raise ValueError("No intraday VIX bars")
        series=frame["Close"].dropna()
        stamp=series.index[-1].to_pydatetime()
        if stamp.tzinfo is None:
            raise ValueError("VIX intraday bar lacks timezone")
        stamp=stamp.astimezone(timezone.utc)
        value=float(series.iloc[-1])
        if not isfinite(value) or value<=0 or stamp>now+timedelta(minutes=1) or now-stamp>timedelta(minutes=30):
            raise ValueError("VIX intraday quote missing or too old")
        indicators=dict(result.get("indicators") or {})
        old=dict(indicators.get("vix") or {})
        history=list(old.get("observations") or [])
        # Keep daily series intact: live quote is a separate temporary overlay.
        indicators["vix"]={**old,"value":value,"observed_at":stamp.isoformat(),
                           "source":"Yahoo Finance VIX 5-minute bar (delayed/not guaranteed real time)",
                           "source_kind":"INTRADAY","observations":history}
        result["indicators"]=indicators
        state["state"]="CURRENT"
        state["observed_at"]=stamp.isoformat()
        state.pop("error",None)
    except Exception as exc:
        state["state"]="UNAVAILABLE"
        state["error"]=str(exc)[:200]
    result["vix_intraday_status"]=state
    return result
