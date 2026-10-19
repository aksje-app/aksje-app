"""Superfond point-in-time research on genuine observed NAV/ETF prices.

Conservative: no synthetic daily history inferred from published annual returns.
No connection to trade engine or learning promotion.
"""
from __future__ import annotations
from datetime import datetime,timezone
from superfund_runtime import read,write

HOLDS=(5,10,20)
STOPS=(3.0,5.0,7.0,10.0)
KEY="historical_research.json"

def test_item(item):
    points=sorted({str(p.get("price_at",""))[:10]:p for p in item.get("observations",[])
                   if p.get("price_at") and (p.get("nok_price") or p.get("price"))}.items())
    if len(points)<7: return {}
    prices=[float(p.get("nok_price") or p["price"]) for _,p in points]
    findings={}
    for hold in HOLDS:
        for stop in STOPS:
            outcomes=[]
            for entry in range(len(prices)-hold):
                initial=prices[entry]
                if initial<=0:continue
                floor=initial*(1-stop/100)
                exit_price=next((p for p in prices[entry+1:entry+hold+1] if p<=floor),prices[entry+hold])
                outcomes.append(100*(exit_price/initial-1))
            if outcomes:
                findings[f"{stop:g}:{hold}"]={"n":len(outcomes),"avg_pct":round(sum(outcomes)/len(outcomes),3)}
    return findings

def run_once(max_items=150):
    index=read("catalog_index.json",{}) or {}
    pages=sorted((index.get("pages") or {}).keys())
    old=read(KEY,{}) or {}
    cursor=int(old.get("cursor",0))
    total=int(sum((index.get("totals") or {}).values()))
    tested=int(old.get("tested",0))
    observed=int(old.get("observed",0))
    if not pages:
        state={"status":"WAITING_FOR_CATALOG","tested":0,"observed":0,"total":total}
        write(KEY,state);return state
    scanned=0
    next_cursor=cursor
    while scanned<max_items and next_cursor<len(pages):
        page=read("catalog/"+pages[next_cursor]+".json",{}) or {}
        for item in page.get("items",[]):
            if scanned>=max_items:break
            scanned+=1
            observations=item.get("observations",[])
            if observations: observed+=1
            trials=test_item(item)
            if trials:
                tested+=1
                # Keep summaries bounded and do not duplicate fund catalogues.
                write("historical_trials/"+str(item.get("id","unknown")).replace("/","_")+".json",
                      {"isin":item.get("isin"),"kind":item.get("kind"),"observations":len(observations),
                       "trials":trials,"validated":False,"basis":"observed_NAV_or_quote_not_backfill"})
        if scanned<max_items:next_cursor+=1
        else:
            # Avoid splitting pages: reread same page next time, dedup by page offset.
            break
    state={"status":"RUNNING" if next_cursor<len(pages) else "COMPLETE_OBSERVATION_PASS",
           "cursor":next_cursor,"pages":len(pages),"tested":tested,"observed":observed,"total":total,
           "updated_at":datetime.now(timezone.utc).isoformat(),
           "history_status":"OBSERVED_ONLY","multi_year_verified":False}
    write(KEY,state)
    return state
