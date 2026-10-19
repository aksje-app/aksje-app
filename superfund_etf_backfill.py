"""Bounded verifiable ETF backfill, no inferred NAV for mutual funds."""
from __future__ import annotations
from datetime import datetime,timezone
from superfund_runtime import read,write
from superfund_identifier_mapping import lookup_isin
from strategy_history_worker import simulate, STOPS, HOLDS
from super_portfolio_market_data import load_price_series_bounded

KEY="etf_backfill.json"

def run_once(limit=8):
    index=read("catalog_index.json",{}) or {}
    pages=sorted((index.get("pages") or {}).keys())
    old=read(KEY,{}) or {}
    cursor=int(old.get("cursor",0))
    checked=int(old.get("checked",0))
    mapped=int(old.get("mapped",0))
    downloaded=int(old.get("downloaded",0))
    unresolved=int(old.get("unresolved",0))
    count=0
    offset=int(old.get("offset",0))
    while cursor<len(pages) and count<limit:
        items=(read("catalog/"+pages[cursor]+".json",{}) or {}).get("items",[])
        done_here=0
        for item in items[offset:]:
            if count>=limit:break
            done_here+=1
            if item.get("kind")!="etf":continue
            count+=1
            checked+=1
            isin=item.get("isin")
            try:
                identity=lookup_isin(isin)
                if identity["status"]!="MAPPED":
                    unresolved+=1
                    continue
                mapped+=1
                symbol=identity["symbol"]
                series,health=load_price_series_bounded(
                    [symbol],"2020-01-01",progress_callback=None,control_callback=None,
                    batch_size=1,max_workers=1)
                bars=series.get(symbol) or []
                if len(bars)<250:
                    unresolved+=1
                    continue
                # One listing per ISIN; do not overwrite market-specific NAV history.
                write("etf_historical_prices/"+isin+".json",
                      {"isin":isin,"identity":identity,"bars":bars,
                       "source":"YAHOO_DAILY_ADJUSTED","verified":False,
                       "qualification":"Exchange quote series; not fund NAV",
                       "downloaded_at":datetime.now(timezone.utc).isoformat()})
                # Separate ETF historical gross-return research from simulated mutual-fund NAV.
                grid = {}
                for stop in STOPS:
                    for hold in HOLDS:
                        returns = simulate(bars, stop, hold)
                        if returns:
                            grid[f"{stop:g}:{hold}"] = {"n":len(returns),"avg_pct":round(sum(returns)/len(returns),3)}
                write("etf_historical_trials/"+isin+".json",
                      {"isin":isin,"symbol":symbol,"trials":grid,"validated":False,
                       "basis":"ETF_DAILY_ADJUSTED_NEXT_OPEN_GROSS_BASELINE"})
                downloaded+=1
            except Exception:
                unresolved+=1
        if done_here<len(items)-offset:
            offset+=done_here
            break
        cursor+=1
        offset=0
    state={"status":"RUNNING" if cursor<len(pages) else "COMPLETE_PASS",
           "checked":checked,"mapped":mapped,"downloaded":downloaded,
           "unresolved":unresolved,"cursor":cursor,"offset":offset,
           "updated_at":datetime.now(timezone.utc).isoformat(),
           "mutual_fund_history":"NOT_AVAILABLE_FROM_THIS_SOURCE"}
    write(KEY,state)
    return state
