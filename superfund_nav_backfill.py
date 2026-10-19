"""Mutual-fund ISIN discovery and NAV history via public Yahoo fund quotes.

A result is accepted only if the search returns one fund with matching ISIN.
Yahoo coverage is partial; a missing/mismatched ISIN is explicitly unresolved.
"""
from __future__ import annotations
import os
from datetime import datetime,timezone
from superfund_runtime import read,write
from superfund_identifier_mapping import isin_valid

KEY="fund_nav_backfill.json"

def resolve_fund(isin, quotes):
    if not isin_valid(isin): return {"status":"INVALID_ISIN"}
    matches=[]
    for row in quotes or []:
        if not isinstance(row,dict):continue
        if str(row.get("quoteType") or "").upper() not in {"MUTUALFUND","MUTUAL_FUND"}:continue
        if str(row.get("isin") or "").upper()!=isin:continue
        symbol=str(row.get("symbol") or "").strip().upper()
        if symbol:matches.append(symbol)
    distinct=sorted(set(matches))
    if len(distinct)!=1:return {"status":"AMBIGUOUS" if distinct else "UNVERIFIED"}
    return {"status":"MAPPED","isin":isin,"symbol":distinct[0],"source":"YAHOO_FUND_SEARCH_EXACT_ISIN"}

def resolve_symbol(isin):
    import yfinance as yf
    search=yf.Search(isin,max_results=20,news_count=0)
    return resolve_fund(isin,getattr(search,"quotes",[]))

def run_once(limit=3):
    from super_portfolio_market_data import load_price_series_bounded
    index=read("catalog_index.json",{}) or {}
    pages=sorted((index.get("pages") or {}).keys())
    old=read(KEY,{}) or {}
    cursor=int(old.get("cursor",0));offset=int(old.get("offset",0))
    checked=int(old.get("checked",0));matched=int(old.get("matched",0))
    downloaded=int(old.get("downloaded",0));unresolved=int(old.get("unresolved",0))
    count=0
    while cursor<len(pages) and count<limit:
        items=(read("catalog/"+pages[cursor]+".json",{}) or {}).get("items",[])
        handled=0
        for item in items[offset:]:
            if count>=limit:break
            handled+=1
            if item.get("kind")!="fond":continue
            count+=1;checked+=1
            isin=str(item.get("isin") or "").upper()
            try:
                identity=resolve_symbol(isin)
                if identity["status"]!="MAPPED":
                    unresolved+=1;continue
                matched+=1
                rows,health=load_price_series_bounded(
                    [identity["symbol"]],"2020-01-01",progress_callback=None,
                    control_callback=None,batch_size=1,max_workers=1)
                bars=rows.get(identity["symbol"]) or []
                if len(bars)<250:
                    unresolved+=1;continue
                # Fund charts use NAV/close only, never pretend intraday stop execution.
                nav=[{"date":x["date"],"nav":x["close"]} for x in bars if x.get("close")]
                if len(nav)<250:
                    unresolved+=1;continue
                write("fund_historical_nav/"+isin+".json",
                      {"isin":isin,"identity":identity,"nav":nav,
                       "source":"YAHOO_FUND_DAILY_CLOSE","verified":False,
                       "updated_at":datetime.now(timezone.utc).isoformat()})
                downloaded+=1
            except Exception:
                unresolved+=1
        if handled < len(items)-offset:
            offset+=handled;break
        cursor+=1;offset=0
    state={"status":"RUNNING" if cursor<len(pages) else "COMPLETE_PASS",
           "cursor":cursor,"offset":offset,"checked":checked,"matched":matched,
           "downloaded":downloaded,"unresolved":unresolved,
           "updated_at":datetime.now(timezone.utc).isoformat(),
           "note":"Only exact-ISIN identified fund NAV; uncovered funds remain unresolved"}
    write(KEY,state)
    return state
