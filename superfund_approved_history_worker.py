"""Opt-in history acquisition from audited symbol manifest and authorized provider."""
from __future__ import annotations
from datetime import datetime,timezone
from superfund_runtime import read,write
from superfund_fmp_history import retrieve_approved

KEY="approved_history_backfill.json"

def run_once(max_items=5):
    manifest=read("approved_history_symbols.json",{}) or {}
    previous=read(KEY,{}) or {}
    if not manifest:
        result={"status":"WAITING_FOR_VERIFIED_MAPPING","approved":0,"downloaded":0,
                "updated_at":datetime.now(timezone.utc).isoformat()}
        write(KEY,result);return result
    catalog=read("catalog_index.json",{}) or {}
    pages=sorted((catalog.get("pages") or {}).keys())
    existing=set(previous.get("processed_isins") or [])
    attempted=0;downloaded=int(previous.get("downloaded") or 0)
    reasons=dict(previous.get("reasons") or {})
    for page in pages:
        for item in (read("catalog/"+page+".json",{}) or {}).get("items",[]):
            isin=str(item.get("isin") or "").upper()
            if isin not in manifest or isin in existing:continue
            if attempted>=max_items:break
            attempted+=1
            answer=retrieve_approved(item,manifest)
            status=answer["status"]
            if status=="READY":
                write("approved_history_prices/"+isin+".json",
                      {"isin":isin,"kind":answer["kind"],"symbol":answer["symbol"],
                       "source":answer["source"],"bars":answer["bars"],
                       "mapping_verified":True,"strategy_validated":False})
                downloaded+=1
            else:reasons[status]=reasons.get(status,0)+1
            if status not in ("WAITING_FOR_FMP_ACCESS",):
                existing.add(isin)
        if attempted>=max_items:break
    result={"status":"RUNNING" if attempted else "WAITING_OR_COMPLETE",
            "approved":len(manifest),"processed":len(existing),
            "downloaded":downloaded,"reasons":reasons,
            "processed_isins":sorted(existing)[:4000],
            "updated_at":datetime.now(timezone.utc).isoformat()}
    write(KEY,result)
    return result
