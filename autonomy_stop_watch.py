"""Quarter-hour read-only stop audit of ALL held Autonomi symbols.

This intentionally NEVER books a trade. Only the established serialized
Autonomi account path may authorize and commit exits.
"""
from __future__ import annotations
from datetime import datetime,timezone,timedelta
import math
from typing import Mapping

from durable_runtime import read_json,write_json
from storage_architecture import runtime_data_path

KEY="autonomous_portfolio/stop_watch.json"
PATH=runtime_data_path("autonomous_portfolio","stop_watch.json")
MAX_QUOTE_AGE_MINUTES=35

def _valid_quote(value, observed_at, now):
    try:
        p=float(value)
        ts=datetime.fromisoformat(str(observed_at).replace("Z","+00:00"))
        if ts.tzinfo is None: return None
        age=(now.astimezone(timezone.utc)-ts.astimezone(timezone.utc)).total_seconds()
        if not math.isfinite(p) or p<=0 or age<0 or age>MAX_QUOTE_AGE_MINUTES*60:return None
        return p
    except (ValueError,TypeError,OverflowError):
        return None

def inspect_positions(positions:Mapping,quotes:Mapping,stop_loss_pct:float,now:datetime):
    alerts=[];missing=[]
    for ticker,pos in sorted(positions.items()):
        row=quotes.get(ticker) or {}
        price=_valid_quote(row.get("price"),row.get("observed_at"),now)
        if price is None:
            missing.append(ticker)
            continue
        entry=float(pos.get("average_price") or 0)
        if entry<=0:missing.append(ticker);continue
        floor=entry*(1-stop_loss_pct/100)
        if price<=floor:
            alerts.append({"ticker":ticker,"price":round(price,4),
                           "entry_price":entry,"stop_price":round(floor,4),
                           "pnl_pct":round((price/entry-1)*100,3),
                           "observed_at":row["observed_at"],"reason":"STOP_LOSS_BREACH"})
    return {"mode":"OBSERVATION_ONLY","checked":len(positions),
            "fresh_quotes":len(positions)-len(missing),
            "missing_or_stale_quotes":missing,"alerts":alerts}

def _download_intraday(tickers:list[str]):
    import yfinance as yf
    from pandas import MultiIndex
    frame=yf.download(tickers,period="1d",interval="5m",progress=False,
                      threads=False,auto_adjust=False,timeout=12,group_by="ticker")
    quotes={}
    for ticker in tickers:
        try:
            part=frame[ticker] if isinstance(frame.columns,MultiIndex) else frame
            closes=part["Close"].dropna()
            if closes.empty:continue
            ts=closes.index[-1]
            if getattr(ts,"tzinfo",None) is None:continue
            quotes[ticker]={"price":float(closes.iloc[-1]),"observed_at":ts.isoformat()}
        except (KeyError,ValueError,IndexError,TypeError):
            continue
    return quotes

def run_due_autonomy_stop_watch():
    from autonomous_portfolio import load_portfolio,load_parameters
    from datetime import datetime,timezone
    now=datetime.now(timezone.utc)
    portfolio=load_portfolio()
    positions=portfolio.get("positions") or {}
    tickers=sorted(str(key) for key in positions)
    previous=read_json(KEY,PATH,{}) or {}
    try:
        last=datetime.fromisoformat(str(previous.get("checked_at") or "").replace("Z","+00:00"))
        if last.tzinfo and now-last<timedelta(minutes=14):
            return {"state":"NOT_DUE","checked_at":previous.get("checked_at")}
    except (ValueError,TypeError):pass
    if not tickers:
        output={"state":"NO_POSITIONS","checked_at":now.isoformat(),"checked":0,
                "mode":"OBSERVATION_ONLY"}
    else:
        try:
            quotes=_download_intraday(tickers)
            audit=inspect_positions(positions,quotes,load_parameters().normalized().stop_loss_pct,now)
            output={"state":"ALERT" if audit["alerts"] else "COMPLETED",
                    "checked_at":now.isoformat(),**audit}
        except Exception as exc:
            output={"state":"PRICE_FETCH_FAILED","checked_at":now.isoformat(),
                    "mode":"OBSERVATION_ONLY","checked":len(tickers),
                    "error":type(exc).__name__}
    write_json(KEY,PATH,output)
    return output
