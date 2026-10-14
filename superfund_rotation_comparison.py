"""Observed-only counterfactual: challenger return minus keeping the owned fund."""
from datetime import date

def _price(row):
    try:
        v=float(row.get("price") or 0)*float(row.get("nok_rate") or 0)
        return v if v>0 else None
    except (TypeError,ValueError):return None

def update_rotation_comparisons(rows, shadow, previous=None, cost_pct=0.6):
    previous=previous or {}
    by_id={r.get("id"):r for r in rows}
    records={}
    for proposal in shadow.get("candidates",[]):
        owner=proposal.get("owned_id"); challenger=proposal.get("challenger_id")
        if not owner or not challenger or proposal.get("status") not in ("CONFIRMING","REVIEW_ONLY"):
            continue
        owned=by_id.get(owner) or {};new=by_id.get(challenger) or {}
        a,b=_price(owned),_price(new)
        da=str(owned.get("price_at") or "")[:10];db=str(new.get("price_at") or "")[:10]
        key=owner+"|"+challenger
        old=previous.get(key) or {}
        # Never combine prices from different NAV dates: this invents a
        # performance advantage when one fund publishes later than the other.
        try:
            valid_dates=bool(date.fromisoformat(da) and date.fromisoformat(db))
        except ValueError:
            valid_dates=False
        if not a or not b or not valid_dates or da!=db:
            records[key]={**old,"status":"AWAITING_MATCHED_NAV","owned_id":owner,
                          "challenger_id":challenger,
                          "evidence_problem":"missing prices or different NAV dates"}
            continue
        evidence_date=da
        if old.get("last_observed_date") and evidence_date<=old["last_observed_date"]:
            records[key]=old
            continue
        if not old.get("entry_owned_nok") or not old.get("entry_challenger_nok"):
            records[key]={"owned_id":owner,"challenger_id":challenger,
                          "entry_date":evidence_date,"last_observed_date":evidence_date,
                          "entry_owned_nok":a,"entry_challenger_nok":b,"observations":1,
                          "net_excess_return_pct":-cost_pct,"status":"BASELINE"}
            continue
        kept_return=100*(a/old["entry_owned_nok"]-1)
        switched_gross=100*(b/old["entry_challenger_nok"]-1)
        excess=switched_gross-kept_return-cost_pct
        records[key]={**old,"last_observed_date":evidence_date,
                      "observations":int(old.get("observations") or 1)+1,
                      "kept_return_pct":round(kept_return,3),
                      "challenger_return_pct":round(switched_gross,3),
                      "net_excess_return_pct":round(excess,3),
                      "status":"MEASURED"}
    # Prevent unbounded snapshot growth: retain only currently tracked comparisons.
    return {"mode":"SHADOW_ONLY","cost_assumption_pct":cost_pct,"pairs":records,
            "measured_count":sum(v.get("status")=="MEASURED" for v in records.values())}
