"""Read-only shadow rotation evaluation; never emits model orders."""
from datetime import datetime, timezone

def _dt(value):
    try:
        dt=datetime.fromisoformat(str(value).replace("Z","+00:00"))
        return dt if dt.tzinfo else None
    except (ValueError,TypeError):return None

def rotation_shadow(rows, positions, now, *, min_days=15, min_gap=1.0):
    by_id={r["id"]:r for r in rows}
    stamp=_dt(now.isoformat() if hasattr(now,"isoformat") else now)
    candidates=[r for r in rows if not r.get("blocks") and r.get("score") is not None and r["id"] not in positions]
    candidates.sort(key=lambda r:-float(r["score"]))
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
        result.append({"owned_id":id,"owned_name":pos.get("name"),"held_days":days,
                       "owned_score":old["score"],"challenger_id":best["id"] if best else None,
                       "challenger_name":best.get("name") if best else None,"score_gap":gap,
                       "status":"REVIEW_ONLY" if eligible else "WATCH",
                       "reason":"Requires consecutive observations, cost, exposure and settlement checks before any decision." if eligible
                       else "Minimum holding period or comparable improvement not established."})
    return {"as_of":stamp.isoformat() if stamp else str(now),"mode":"SHADOW_ONLY",
            "candidates":result,"review_count":sum(r["status"]=="REVIEW_ONLY" for r in result)}
