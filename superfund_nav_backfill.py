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

def resolve_symbol(isin, name=""):
    import yfinance as yf
    searches=[isin]
    if name and name.strip(): searches.append(name[:80])
    for term in searches:
        search=yf.Search(term,max_results=20,news_count=0)
        direct=resolve_fund(isin,getattr(search,"quotes",[]))
        if direct["status"]=="MAPPED":return direct
        # Yahoo search often omits ISIN even for genuine mutual funds.
        # Confirm using the instrument's own ISIN field; names never suffice.
        for quote in (getattr(search,"quotes",[]) or [])[:8]:
            if str(quote.get("quoteType") or "").upper()!="MUTUALFUND":continue
            ticker=str(quote.get("symbol") or "")
            if not ticker:continue
            try:
                actual=str(yf.Ticker(ticker).isin or "").upper()
            except Exception:
                continue
            if actual==isin:
                return {"status":"MAPPED","isin":isin,"symbol":ticker,
                        "source":"YAHOO_TICKER_VERIFIED_ISIN"}
    return {"status":"UNVERIFIED"}

def run_once(limit=3):
    from super_portfolio_market_data import load_price_series_bounded
    index=read("catalog_index.json",{}) or {}
    pages=sorted((index.get("pages") or {}).keys())
    old=read(KEY,{}) or {}
    cursor=int(old.get("cursor",0));offset=int(old.get("offset",0))
    checked=int(old.get("checked",0));matched=int(old.get("matched",0))
    downloaded=int(old.get("downloaded",0));unresolved=int(old.get("unresolved",0))
    reasons=dict(old.get("failure_reasons") or {})
    # Avoid repeated failed provider requests once evidence shows zero usable mappings.
    if checked >= 30 and downloaded == 0 and (mapped if "mapped" in locals() else matched) == 0:
        state={**old,"status":"BLOCKED_IDENTITY_SOURCE",
               "reason":"No verified ISIN to historical-symbol mappings in first 30 requests; automated calls paused",
               "updated_at":datetime.now(timezone.utc).isoformat()}
        write(KEY,state)
        return state
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
            failure="UNKNOWN"
            try:
                identity=resolve_symbol(isin,item.get("name",""))
                if identity["status"]!="MAPPED":
                    failure=identity.get("status","UNRESOLVED") if identity.get("status")!="MAPPED" else "INSUFFICIENT_HISTORY"
                    unresolved+=1;reasons[failure]=reasons.get(failure,0)+1;continue
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
            except Exception as exc:
                reason="SOURCE_"+type(exc).__name__.upper()
                reasons[reason]=reasons.get(reason,0)+1
                unresolved+=1
        if handled < len(items)-offset:
            offset+=handled;break
        cursor+=1;offset=0
    state={"status":"RUNNING" if cursor<len(pages) else "COMPLETE_PASS",
           "cursor":cursor,"offset":offset,"checked":checked,"matched":matched,
           "downloaded":downloaded,"unresolved":unresolved,"failure_reasons":reasons,
           "updated_at":datetime.now(timezone.utc).isoformat(),
           "note":"Only exact-ISIN identified fund NAV; uncovered funds remain unresolved"}
    write(KEY,state)
    return state
