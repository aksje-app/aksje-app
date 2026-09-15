from __future__ import annotations
from datetime import datetime,timezone
from typing import Any,Mapping

def candidate_change_kind(candidate: Mapping[str,Any], previous: Mapping[str,Any] | None) -> str:
    if previous is None: return "NEW"
    keys=("score","decision","action","rank","reason","decision_reason")
    return "CHANGED" if any(candidate.get(k)!=previous.get(k) for k in keys) else "UNCHANGED"

def build_market_view(run: Mapping[str,Any],status: Mapping[str,Any],now: datetime | None=None) -> dict[str,Any]:
    run_id=str(run.get("run_id") or ""); latest=str(status.get("latest_successful_run_id") or "")
    terminal=str(status.get("state") or "").upper() in {"COMPLETED","DEGRADED"}
    publish=bool(terminal and run_id and run_id==latest)
    return {"run_id":run_id,"publish_now":publish,"freshness_state":"FRESH" if publish else "STALE","candidates":list(run.get("candidates") or []),"completed_at":str(run.get("completed_at") or "")}
