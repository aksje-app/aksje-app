from __future__ import annotations
from typing import Any,Mapping,Sequence
from .models import DecisionView

def build_decision_diagnostics(candidates: Sequence[Mapping[str,Any]]) -> list[DecisionView]:
    return [DecisionView.from_mapping(c) for c in candidates]

def build_autonomy_view(snapshot: Mapping[str,Any]) -> dict[str,Any]:
    last=snapshot.get("last_run") or snapshot.get("latest_run") or {}
    return {"last_completed_at":str(last.get("completed_at") or last.get("finished_at") or "-"),"next_run_at":str(snapshot.get("next_run_at") or (snapshot.get("next_run") or {}).get("at") or "-"),"candidates_evaluated":int(last.get("candidates_evaluated") or 0),"decisions":int(last.get("decisions") or 0),"health":str(snapshot.get("health") or (snapshot.get("status") or {}).get("health") or "UKJENT")}

def parameter_proposal_view(proposal: Mapping[str,Any]) -> dict[str,Any]:
    return {"proposal_id":str(proposal.get("proposal_id") or proposal.get("id") or ""),"before":proposal.get("before_value",proposal.get("before","-")),"after":proposal.get("after_value",proposal.get("after","-")),"evidence":proposal.get("evidence") or [],"state":str(proposal.get("state") or "PENDING")}
