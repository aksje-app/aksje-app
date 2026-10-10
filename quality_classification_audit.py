"""Read-only audit of stored assessments; no historical record is rewritten."""
from collections import Counter
from quality_valuation import evaluate_company
from quality_turnaround import date


def audit_snapshots(snapshots):
    counts = Counter()
    affected = {}
    checked, unavailable = 0, 0
    for snapshot in snapshots:
        for items in (snapshot.get("groups") or {}).values():
            for row in items:
                as_of = date(row.get("observed_at") or snapshot.get("generated_at"))
                if not as_of or not row.get("ticker"):
                    unavailable += 1
                    continue
                raw = {**row, "annual_eps": row.get("annual_eps_history") or [],
                       "roce_history": [x / 100 for x in row.get("roce_history_pct") or []],
                       "roce": row.get("roce_latest_pct") / 100 if row.get("roce_latest_pct") is not None else None}
                try:
                    new = evaluate_company(raw, assumed_pe=row.get("assumed_pe"), as_of=as_of)
                except ValueError:
                    unavailable += 1
                    continue
                checked += 1
                if row.get("review_reason_category") == "MISSING_DATA" and new["review_reason_category"] == "NONPOSITIVE_HISTORICAL_EARNINGS":
                    counts[new["sector_policy"]] += 1
                    affected[row["ticker"]] = {"ticker": row["ticker"], "sector_policy": new["sector_policy"],
                                               "old_reason": "MISSING_DATA", "correct_reason": new["review_reason_category"],
                                               "historical_eps_median": new["historical_eps_median"],
                                               "run_key": snapshot.get("run_key"), "observed_at": as_of.isoformat()}
    return {"schema": "quality-classification-audit@1.0", "read_only": True,
            "checked_assessments": checked, "unavailable_assessments": unavailable,
            "affected_assessments_by_policy": dict(counts), "affected_unique_tickers": list(affected.values()),
            "limitation": "Stored available evidence only; no historical source data or missing periods reconstructed"}


def audit_storage(storage, *, max_runs=500, progress=None, memory_guard=None, deadline_seconds=30):
    import re
    import time
    started = time.monotonic()
    names = sorted((key for key in storage.list_json_names()
                    if re.fullmatch(r"quality_valuation/runs/\d{8}T\d{12}", key)), reverse=True)
    limit = max(1, min(int(max_runs), 1000))
    examined = [0]
    stop_reason = [""]
    def snapshots():
        for key in names[:limit]:
            if time.monotonic() - started >= deadline_seconds or (memory_guard and not memory_guard()):
                stop_reason[0] = "RESOURCE_OR_DEADLINE"
                break
            value = storage.read_json(key, {})
            examined[0] += 1
            if progress:
                progress(examined[0], min(limit, len(names)))
            if isinstance(value, dict):
                yield value
    result = audit_snapshots(snapshots())
    result.update(available_runs=len(names), examined_runs=examined[0], coverage_complete=examined[0] == len(names), stop_reason=stop_reason[0])
    return result
