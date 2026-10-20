"""Optional documented FMP daily-history adapter for audited ISIN-to-symbol mappings.

Requires an operator-reviewed per-ISIN symbol manifest and FMP_API_KEY.
Never guesses tickers from names or uses published period returns as daily NAV.
"""
from __future__ import annotations
from datetime import date
import json
import os
import re
from urllib.parse import urlencode
from urllib.request import Request,urlopen

def approved_symbol(isin, kind, manifest):
    row=(manifest or {}).get(str(isin or "").upper())
    if not isinstance(row,dict):return None
    if row.get("isin")!=isin or row.get("kind")!=kind or row.get("verified") is not True:
        return None
    symbol=str(row.get("symbol") or "").strip().upper()
    if not re.fullmatch(r"[A-Z0-9.\\-^]{1,24}",symbol):return None
    if not row.get("evidence_url") or not str(row["evidence_url"]).startswith("https://"):
        return None
    return symbol

def fetch_history(symbol,kind,*,api_key, opener=urlopen):
    if not api_key:raise ValueError("FMP_API_KEY_MISSING")
    if kind not in ("fond","etf"):raise ValueError("KIND_UNSUPPORTED")
    if not re.fullmatch(r"[A-Z0-9.\\-^]{1,24}",symbol):raise ValueError("SYMBOL_INVALID")
    # FMP documents daily mutual-fund history. Its legacy path may require a plan.
    url="https://financialmodelingprep.com/api/v3/historical-price-full/"+symbol+"?"+urlencode({"apikey":api_key})
    with opener(Request(url,headers={"Accept":"application/json"}),timeout=18) as response:
        payload=json.load(response)
    if not isinstance(payload,dict) or str(payload.get("symbol","")).upper()!=symbol:
        raise ValueError("FMP_SYMBOL_MISMATCH_OR_ACCESS_DENIED")
    observations=payload.get("historical")
    if not isinstance(observations,list):raise ValueError("FMP_NO_DAILY_HISTORY")
    dates={}
    for point in observations:
        if not isinstance(point,dict):continue
        try:
            dt=date.fromisoformat(str(point["date"]))
            close=float(point["close"])
        except (KeyError,ValueError,TypeError):continue
        if not 0<close<1e9:continue
        dates[dt.isoformat()]=round(close,8)
    return [{"date":d,"nav" if kind=="fond" else "close":v} for d,v in sorted(dates.items())]

def retrieve_approved(item, manifest, *, opener=urlopen):
    isin=str(item.get("isin") or "").upper()
    kind=str(item.get("kind") or "")
    symbol=approved_symbol(isin,kind,manifest)
    if not symbol:return {"status":"WAITING_FOR_VERIFIED_MAPPING"}
    api_key=os.getenv("FMP_API_KEY","")
    if not api_key:return {"status":"WAITING_FOR_FMP_ACCESS"}
    try:bars=fetch_history(symbol,kind,api_key=api_key,opener=opener)
    except Exception as exc:
        # No API credential or raw provider responses in persisted diagnostics.
        return {"status":"PROVIDER_"+type(exc).__name__.upper()}
    if len(bars)<250:return {"status":"INSUFFICIENT_DAILY_HISTORY","points":len(bars)}
    return {"status":"READY","isin":isin,"kind":kind,"symbol":symbol,
            "source":"FMP_DAILY_HISTORICAL","bars":bars,"verified_mapping":True}
