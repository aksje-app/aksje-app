"""Full-market pre-screen for the manual quality/valuation workflow."""
from __future__ import annotations
from typing import Any, Callable, Mapping, Sequence
from candidate_market_data import enrich_candidate_rows

def _num(value: Any) -> float | None:
    try:
        n=float(value)
        return n if n == n and abs(n) != float("inf") else None
    except (TypeError, ValueError):
        return None

def _clamp(value: float) -> float:
    return max(0.0, min(100.0, float(value)))

def prescreen_score(row: Mapping[str, Any]) -> float:
    keys=("last_price","trailing_pe","roe","debt_to_equity","earnings_growth","revenue_growth","momentum_score","trend_score")
    coverage=sum(row.get(k) not in (None,"") for k in keys)/len(keys)
    pe=_num(row.get("trailing_pe")); pe_score=50.0 if pe is None or pe<=0 else _clamp(100-abs(pe-16)*3)
    roe=_num(row.get("roe")); roe_score=50.0 if roe is None else _clamp(roe*2.5)
    debt=_num(row.get("debt_to_equity")); debt_score=50.0 if debt is None else _clamp(100-max(0,debt)*0.5)
    growth=[x for x in (_num(row.get("earnings_growth")),_num(row.get("revenue_growth"))) if x is not None]
    growth_score=50.0 if not growth else _clamp(50+sum(growth)/len(growth))
    market=[x for x in (_num(row.get("momentum_score")),_num(row.get("trend_score"))) if x is not None]
    market_score=50.0 if not market else _clamp(sum(market)/len(market))
    return round(roe_score*.25+pe_score*.25+debt_score*.15+growth_score*.20+market_score*.05+coverage*100*.10,2)

def full_market_prescreen(tickers: Sequence[str], finalist_limit: int=20, *, progress: Callable[[int,int,str],None]|None=None, chunk_size: int=60) -> dict[str,Any]:
    universe=list(dict.fromkeys(str(x or "").strip().upper() for x in tickers if str(x or "").strip()))
    limit=max(1,min(int(finalist_limit or 20),20)); rows=[]; total=len(universe); completed=0
    for start in range(0,total,max(1,int(chunk_size))):
        chunk=universe[start:start+max(1,int(chunk_size))]
        input_rows=[{"ticker": ticker} for ticker in chunk]
        enriched=enrich_candidate_rows(input_rows,max_workers=6,force_refresh=False)
        by_ticker={str(row.get("ticker") or "").upper():dict(row) for row in enriched}
        for ticker in chunk:
            row=by_ticker.get(ticker,{"ticker":ticker,"data_fetch_status":"ERROR","data_fetch_error":"Mangler resultat"})
            row["quality_prescreen_score"]=prescreen_score(row); rows.append(row); completed+=1
            if progress: progress(completed,total,ticker)
    usable=[r for r in rows if str(r.get("data_fetch_status") or "").upper() not in {"ERROR","QUARANTINED"} and r.get("last_price") not in (None,"")]
    usable.sort(key=lambda r:(float(r.get("quality_prescreen_score") or 0),len(r.get("raw_fields_available") or [])),reverse=True)
    failures=[r for r in rows if str(r.get("data_fetch_status") or "").upper() in {"ERROR","QUARANTINED"}]
    return {"universe_count":total,"examined_count":len(rows),"usable_count":len(usable),"failed_count":len(failures),"complete":len(rows)==total and not failures,"finalist_limit":limit,"finalists":[str(r.get("ticker") or "") for r in usable[:limit] if r.get("ticker")],"rows":rows}
