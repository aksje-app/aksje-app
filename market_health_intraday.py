"""Session-aware, read-only intraday market overlays.

Daily archived observations remain untouched. Intraday quotes are labelled
as potentially delayed. No trading signals or automatic order actions.
"""
from datetime import datetime, timedelta, timezone, time
from zoneinfo import ZoneInfo
from math import isfinite

NY=ZoneInfo("America/New_York")
LONDON=ZoneInfo("Europe/London")
# Only quote-bearing Yahoo instruments. Daily macro and breadth series stay daily.
MARKETS={
    "us10y":("^TNX","NY"),
    "us30y":("^TYX","NY"),
    "gold":("GC=F","GLOBAL"),
    "brent":("BZ=F","GLOBAL"),
    "dxy":("DX-Y.NYB","NY"),
    "eurusd":("EURUSD=X","FX"),
    "ttf":("TTF=F","EU"),
}

def in_session(key, now):
    if key not in MARKETS:
        return False
    market=MARKETS[key][1]
    ny=now.astimezone(NY)
    eu=now.astimezone(LONDON)
    if market=="NY":
        return ny.weekday()<5 and time(9,30)<=ny.time()<time(16,0)
    if market=="EU":
        return eu.weekday()<5 and time(8,0)<=eu.time()<time(18,0)
    # Approximate provider polling windows, not an exchange holiday calendar.
    if market=="FX":
        return (ny.weekday()<5 and not (ny.weekday()==4 and ny.time()>=time(17,0))) or (ny.weekday()==6 and ny.time()>=time(17,0))
    return (ny.weekday()<5 and not (ny.weekday()==4 and ny.time()>=time(17,0))) or (ny.weekday()==6 and ny.time()>=time(18,0))

def update_intraday(snapshot, *, now=None, provider=None):
    now=now or datetime.now(timezone.utc)
    result=dict(snapshot or {})
    states=dict(result.get("intraday_status") or {})
    indicators=dict(result.get("indicators") or {})
    for key,(symbol,_) in MARKETS.items():
        previous=dict(indicators.get(key) or {})
        state=dict(states.get(key) or {})
        if not in_session(key,now):
            if previous.get("source_kind")=="INTRADAY":
                rows=previous.get("observations") or []
                if rows:
                    daily=max(rows,key=lambda r:r["observed_at"])
                    indicators[key]={**daily,"observations":rows}
            state["state"]="MARKET_CLOSED"
            states[key]=state
            continue
        try:
            last=datetime.fromisoformat(str(state.get("attempt_at")).replace("Z","+00:00"))
            if last.tzinfo and now-last<timedelta(minutes=30):
                states[key]=state
                continue
        except (TypeError,ValueError):
            pass
        state["attempt_at"]=now.isoformat()
        try:
            if provider is None:
                import yfinance as yf
                frame=yf.Ticker(symbol).history(period="1d",interval="5m",auto_adjust=False)
            else:
                frame=provider(key,symbol)
            if frame is None or frame.empty or "Close" not in frame:
                raise ValueError("Missing provider intraday bars")
            series=frame["Close"].dropna()
            at=series.index[-1].to_pydatetime()
            if at.tzinfo is None:
                raise ValueError("Unqualified quote timestamp")
            at=at.astimezone(timezone.utc)
            value=float(series.iloc[-1])
            if not isfinite(value) or value<=0 or at>now+timedelta(minutes=1) or now-at>timedelta(minutes=35):
                raise ValueError("Intraday quote stale or invalid")
            indicators[key]={**previous,"value":value,"observed_at":at.isoformat(),
                             "source":f"Yahoo 5m potentially delayed ({symbol})",
                             "source_kind":"INTRADAY"}
            state["state"]="CURRENT"
            state["observed_at"]=at.isoformat()
            state.pop("error",None)
        except Exception as exc:
            state["state"]="UNAVAILABLE"
            state["error"]=str(exc)[:180]
        states[key]=state
    result["indicators"]=indicators
    result["intraday_status"]=states
    return result
