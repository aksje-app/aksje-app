"""Read-only, reproducible autonomy trade-loss diagnosis.

Historical trade outcomes alone do not establish counterfactual performance.
"""
from collections import defaultdict
from statistics import mean

def diagnose(trades):
    buys=[r for r in trades if r.get("action")=="BUY"]
    closes=[r for r in trades if r.get("action") in ("SELL","SELL_PARTIAL")]
    groups=defaultdict(list)
    for row in closes:
        reason=str(row.get("reason") or "").split(":",1)[0].strip()
        groups[reason].append(row)
    reasons={}
    for reason,rows in sorted(groups.items()):
        pnl=[float(r.get("pnl") or 0) for r in rows]
        days=[float(r["holding_days"]) for r in rows if r.get("holding_days") is not None]
        reasons[reason]={"trades":len(rows),"pnl":round(sum(pnl),2),
                         "average_holding_days":round(mean(days),2) if days else None,
                         "losses":sum(v<0 for v in pnl)}
    missing_timing=sum(not r.get("technical_timing") for r in buys)
    return {"buy_count":len(buys),"closed_count":len(closes),
            "missing_technical_timing":missing_timing,
            "reasons":reasons,"counterfactual_validated":False,
            "limitations":["Closed trades are selected outcomes: rejected or delayed buys have no recorded fills.",
                           "Entry-hour, stop-distance and regime changes require point-in-time quote paths.",
                           "Do not infer causal improvements or modify production parameters from this report."]}
