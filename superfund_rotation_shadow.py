"""Read-only shadow rotation evaluation; never emits model orders."""
from datetime import datetime, timezone

def _dt(value):
    try:
        dt=datetime.fromisoformat(str(value).replace("Z","+00:00"))
        return dt if dt.tzinfo else None
    except (ValueError,TypeError):return None

def _holdings(row):
    holdings=row.get("holdings") or (row.get("detail") or {}).get("holdings") or []
    return {str(x.get("isin") or x.get("name") or "").upper():float(x.get("weight") or 0)
            for x in holdings if isinstance(x,dict) and (x.get("isin") or x.get("name"))}

def _overlap(a,b):
    left,right=_holdings(a),_holdings(b)
    if not left or not right:return None
    return round(sum(min(v,right.get(k,0)) for k,v in left.items()),2)

def rotation_shadow(rows, positions, now, *, min_days=15, min_gap=1.0, previous=None,
                    min_confirmations=3, estimated_roundtrip_pct=0.6):
    by_id={r["id"]:r for r in rows}
    stamp=_dt(now.isoformat() if hasattr(now,"isoformat") else now)
    candidates=[r for r in rows if not r.get("blocks") and r.get("score") is not None and r["id"] not in positions]
    candidates.sort(key=lambda r:-float(r["score"]))
    previous=previous or {}
    result=[]
    for id,pos in positions.items():
        old=by_id.get(id)
        bought=_dt(pos.get("bought_at"))
        days=(stamp.date()-bought.date()).days if stamp and bought else None
        if not old or old.get("score") is None:
            result.append({"owned_id":id,"status":"INSUFFICIENT_DATA","held_days":days})
            continue
        comparable=[r for r in candidates if r.get("category")==old.get("category") and
                    r.get("returns_currency")==old.get("returns_currency")]
        best=comparable[0] if comparable else None
        gap=float(best["score"])-float(old["score"]) if best else None
        eligible=days is not None and days>=min_days and gap is not None and gap>=min_gap
        prior=previous.get(id) or {}
        # Require fresh observed NAV dates for BOTH funds, not repeated scans.
        owned_date=str(old.get("price_at") or "")[:10]
        new_date=str(best.get("price_at") or "")[:10] if best else ""
        from datetime import date
        try:
            matched=bool(date.fromisoformat(owned_date) and date.fromisoformat(new_date)) and owned_date==new_date
        except ValueError:
            matched=False
        evidence_date=owned_date if matched else ""
        prior_date=str(prior.get("evidence_date") or "")
        fresh=bool(evidence_date and (not prior_date or evidence_date>prior_date))
        consecutive=eligible and prior.get("challenger_id")==best["id"]
        if eligible and fresh:
            confirmations=(int(prior.get("confirmations") or 0)+1 if consecutive else 1)
        elif eligible and evidence_date==prior_date and consecutive:
            confirmations=int(prior.get("confirmations") or 0)
        else:
            confirmations=0
        overlap=_overlap(old,best) if best else None
        price=pos.get("last_nok")
        size=pos.get("quantity")
        try:estimated_cost_nok=round(float(price)*float(size)*estimated_roundtrip_pct/100,2)
        except (ValueError,TypeError):estimated_cost_nok=None
        # Do not present stale or future-dated NAV as a current recommendation.
        age=(stamp.date()-date.fromisoformat(evidence_date)).days if stamp and evidence_date else None
        usable=age is not None and 0<=age<=7
        if not usable:confirmations=0
        confirmed=eligible and usable and confirmations>=min_confirmations
        status="REVIEW_ONLY" if confirmed else "CONFIRMING" if eligible and usable else "STALE_NAV" if eligible else "WATCH"
        result.append({"owned_id":id,"owned_name":pos.get("name"),"held_days":days,
                       "owned_score":old["score"],"challenger_id":best["id"] if best else None,
                       "challenger_name":best.get("name") if best else None,"score_gap":gap,
                       "status":status,"confirmations":confirmations,"required_confirmations":min_confirmations,
                       "last_date":stamp.date().isoformat() if stamp else None, "evidence_date":evidence_date,
                       "nav_age_days":age,
                       "known_holdings_overlap_pct":overlap,"estimated_roundtrip_cost_nok":estimated_cost_nok,
                       "cost_assumption_pct":estimated_roundtrip_pct,
                       "reason":"Advisory only: confirm net benefit, missing overlap, prices and settlement before any decision." if confirmed
                       else "Minimum holding period or comparable improvement not established."})
    return {"as_of":stamp.isoformat() if stamp else str(now),"mode":"SHADOW_ONLY",
            "candidates":result,"review_count":sum(r["status"]=="REVIEW_ONLY" for r in result)}
