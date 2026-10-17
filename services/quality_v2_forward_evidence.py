"""Read-only Quality V2 forward-return evaluation; no trading side effects."""
from collections import defaultdict
from datetime import date
from math import isfinite


def compare_quality_v2_forward(rows, marks_by_ticker, *, sessions=(7, 30)):
    """Compare baseline and V2 classifications from the SAME decision date.

    marks_by_ticker contains chronological unique dated close records. Entries
    at or before decision_date are never counted as forward observations.
    """
    groups = defaultdict(list)
    rejected = defaultdict(int)
    for row in rows:
        ticker = str(row.get("ticker") or "")
        direction = str(row.get("comparison_direction") or "")
        decision = str(row.get("decision_date") or "")[:10]
        entry = row.get("entry_price")
        try:
            date.fromisoformat(decision)
            entry = float(entry)
            if not isfinite(entry) or entry <= 0:
                raise ValueError("invalid entry")
        except (ValueError, TypeError):
            rejected["MISSING_DECISION_DATE_OR_ENTRY_PRICE"] += 1
            continue
        observations = sorted(marks_by_ticker.get(ticker, []), key=lambda m: str(m.get("market_date") or ""))
        future = []
        seen = set()
        for mark in observations:
            day = str(mark.get("market_date") or "")[:10]
            if day <= decision or day in seen:
                continue
            try:
                price = float(mark["adjusted_close"])
                date.fromisoformat(day)
                if not isfinite(price) or price <= 0:
                    raise ValueError("bad price")
            except (ValueError, TypeError, KeyError):
                continue
            seen.add(day)
            future.append(price)
        for horizon in sessions:
            if len(future) < horizon:
                rejected[f"INSUFFICIENT_{horizon}_SESSIONS"] += 1
                continue
            value = (future[horizon - 1] / entry - 1.0) * 100
            groups[(direction, horizon)].append(value)
    return {"cohorts": [
        {"comparison_direction": direction, "sessions": horizon,
         "count": len(values), "mean_return_pct": round(sum(values) / len(values), 4),
         "positive_count": sum(x > 0 for x in values)}
        for (direction, horizon), values in sorted(groups.items())],
        "rejected": dict(rejected), "shadow_only": True,
        "production_promotion_allowed": False,
        "caveat": "Requires historical adjusted entry and forward closes plus filing-date provenance"}
