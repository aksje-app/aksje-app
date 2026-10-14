"""Read-only competitor triage for Superfond alerts; does not decide trades."""
from collections import Counter

def _score(row):
    try:
        value=row.get("score")
        return float(value) if value is not None else None
    except (ValueError,TypeError):return None

def evaluate_challengers(rows, positions, previous=None, *, top_n=25):
    """Compare candidates in the *same category and return currency*.

    Rank across unlike currencies is presented for discovery only, not a
    comparable performance claim. Unknown evidence never passes the gate.
    """
    previous=previous or {}
    qualified=[r for r in rows if not r.get("blocks") and _score(r) is not None]
    ordered=sorted(qualified,key=lambda r:(-_score(r),str(r.get("id"))))
    ranks={r["id"]:i for i,r in enumerate(ordered,1)}
    owned=[r for r in rows if r.get("id") in positions and _score(r) is not None]
    reports=[]
    for row in ordered:
        if row["id"] in positions:continue
        score=_score(row)
        comparable=[r for r in owned if r.get("category")==row.get("category")
                    and r.get("returns_currency")==row.get("returns_currency")]
        better=sum(score>_score(p) for p in comparable)
        same_group=[r for r in qualified if r.get("category")==row.get("category") and r.get("returns_currency")==row.get("returns_currency")]
        group_rank=1+sum(_score(r)>score for r in same_group)
        prior=previous.get(row["id"],{})
        prior_rank=prior.get("rank")
        climbing=isinstance(prior_rank,int) and prior_rank-ranks[row["id"]]>=10
        relevant=(ranks[row["id"]]<=top_n and (better>0 or not comparable))
        early=climbing and ranks[row["id"]]<=top_n+10
        # Do not claim a true swap advantage when region/holdings are unavailable.
        reports.append({"id":row["id"],"name":row.get("name"),"score":score,
                        "rank":ranks[row["id"]],"total":len(ordered),
                        "category_rank":group_rank,"same_group_held":len(comparable),
                        "outperforms_held":better,"candidate":relevant,
                        "early_watch":early,"rank_gain":prior_rank-ranks[row["id"]] if isinstance(prior_rank,int) else None,
                        "reason":"Sterkere enn sammenlignbart eid fond" if better else
                                 "Toppkandidat uten sammenlignbart eid fond" if relevant else
                                 "Kun intern observasjon"})
    return {"rows":reports[:150],"totals":{"evaluated":len(ordered),"prioritized":sum(r["candidate"] for r in reports),
                                           "early_watch":sum(r["early_watch"] for r in reports),
                                           "filtered":sum(not r["candidate"] for r in reports)},
            "rank_history":{r["id"]:{"rank":r["rank"]} for r in reports[:150]}}
