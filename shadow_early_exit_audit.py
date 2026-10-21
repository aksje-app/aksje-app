"""Read-only cohort audit for simulated trades; no execution or rule changes."""
from collections import defaultdict
from statistics import mean, median
from datetime import datetime

def _num(value):
    try:
        return float(value) if value is not None else None
    except (TypeError, ValueError):
        return None

def _days(row):
    if row.get("holding_days") is not None:
        return _num(row.get("holding_days"))
    try:
        entry = datetime.fromisoformat(str(row["entry_at"]).replace("Z", "+00:00"))
        exit_ = datetime.fromisoformat(str(row["exit_at"]).replace("Z", "+00:00"))
        return (exit_ - entry).total_seconds()/86400
    except (KeyError, ValueError, TypeError):
        return None

def audit_closed_shadow_trades(rows):
    """Use only verified closed-trade evidence; never infer missing costs."""
    buckets = defaultdict(list)
    missing = {"holding_period":0, "prices":0, "costs":0}
    details=[]
    for row in rows:
        days=_days(row)
        buy=_num(row.get("entry_price"))
        sell=_num(row.get("exit_price"))
        if days is None or days < 0:
            missing["holding_period"]+=1
            continue
        if buy is None or sell is None or buy<=0 or sell<=0:
            missing["prices"]+=1
            continue
        cost=_num(row.get("total_cost_pct"))
        if cost is None:
            missing["costs"]+=1
        gross=100*(sell/buy-1)
        net=gross-cost if cost is not None else None
        bucket="same_day" if days<1 else "next_day" if days<2 else "days_2_5" if days<6 else "days_6_plus"
        item={"symbol":str(row.get("symbol") or ""), "holding_days":round(days,3), "gross_pct":round(gross,4),
              "net_pct":round(net,4) if net is not None else None, "cost_verified":cost is not None,
              "exit_reason":row.get("exit_reason"), "entry_signal_at":row.get("entry_signal_at"),
              "entry_at":row.get("entry_at"), "exit_at":row.get("exit_at"), "stop_price":row.get("stop_price"),
              "peak_price":row.get("peak_price"), "quote_at":row.get("quote_at")}
        buckets[bucket].append(item)
        details.append(item)
    summary={}
    for name in ("same_day","next_day","days_2_5","days_6_plus"):
        group=buckets[name]
        complete=[r["net_pct"] for r in group if r["net_pct"] is not None]
        summary[name]={"count":len(group), "net_sample":len(complete),
                       "net_mean_pct":round(mean(complete),3) if complete else None,
                       "net_median_pct":round(median(complete),3) if complete else None,
                       "net_win_rate_pct":round(100*sum(v>0 for v in complete)/len(complete),2) if complete else None}
    return {"read_only":True, "summary":summary, "missing":missing, "rows":details}
