"""Conservative ISIN -> listed ETF identity mapping via documented OpenFIGI v3 API.

Unresolved or ambiguous IDs are not allowed into price acquisition.
OpenFIGI is an identifier source, NOT a NAV/price data source.
"""
from __future__ import annotations
import json
import os
import re
from urllib.request import Request,urlopen

API="https://api.openfigi.com/v3/mapping"
SUFFIX={"US":"","LN":".L","LONDON":".L","SW":".SW","SWISS":".SW",
        "GY":".DE","GR":".DE","GERMANY":".DE","FP":".PA","FRANCE":".PA",
        "SS":".ST","SWEDEN":".ST","DC":".CO","DENMARK":".CO",
        "FH":".HE","FINLAND":".HE","NO":".OL","NORWAY":".OL"}

def isin_valid(isin):
    return bool(re.fullmatch(r"[A-Z]{2}[A-Z0-9]{9}[0-9]",str(isin or "")))

def resolve_mapping(isin, candidates):
    if not isin_valid(isin):return {"status":"INVALID_ISIN"}
    unique={}
    for row in candidates or []:
        if not isinstance(row,dict):continue
        ticker=str(row.get("ticker") or "").strip().upper()
        exchange=str(row.get("exchCode") or "").strip().upper()
        sector=str(row.get("marketSector") or "").upper()
        kind=str(row.get("securityType2") or row.get("securityType") or "").upper()
        if not ticker or not exchange or not any(term in kind for term in ("ETF","EXCHANGE TRADED FUND")):
            continue
        if sector not in ("EQUITY","FUNDS",""):continue
        suffix=SUFFIX.get(exchange)
        if suffix is None:continue
        yahoo=ticker.replace(" ","-")+suffix
        unique[(ticker,exchange)]=yahoo
    # Same ISIN may be exchange-listed in multiple currencies/venues.
    # Multiple FIGI listings of the same ticker/venue do not create ambiguity.\n    if len(unique)!=1:return {"status":"AMBIGUOUS" if unique else "UNRESOLVED","options":len(unique)}
    (ticker,exchange),symbol=next(iter(unique.items()))
    return {"status":"MAPPED","isin":isin,"ticker":ticker,"exchange":exchange,
            "symbol":symbol,"identity_source":"OPENFIGI_ID_ISIN"}

def lookup_isin(isin):
    if not isin_valid(isin):return {"status":"INVALID_ISIN"}
    headers={"Content-Type":"application/json","Accept":"application/json"}
    if os.getenv("OPENFIGI_API_KEY"):headers["X-OPENFIGI-APIKEY"]=os.environ["OPENFIGI_API_KEY"]
    req=Request(API,data=json.dumps([{"idType":"ID_ISIN","idValue":isin}]).encode(),
                headers=headers,method="POST")
    with urlopen(req,timeout=12) as response:
        if response.status!=200:raise ValueError("OpenFIGI response error")
        result=json.load(response)
    if not isinstance(result,list) or len(result)!=1:raise ValueError("OpenFIGI schema mismatch")
    entry=result[0]
    if entry.get("error"):
        return {"status":"PROVIDER_REJECTED","reason":str(entry["error"])[:120]}
    return resolve_mapping(isin,entry.get("data",[]))
