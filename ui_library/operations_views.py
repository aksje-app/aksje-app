from __future__ import annotations
from typing import Any,Mapping,Sequence

def severity_for(item: Mapping[str,Any]) -> str:
    kind=str(item.get("kind") or "").upper(); state=str(item.get("state") or "").upper()
    if kind=="RUNTIME_IDENTITY" and item.get("aligned") is False: return "danger"
    if state in {"FAILED","ERROR","BLOCKED","CRITICAL"}: return "danger"
    if state in {"WARNING","DEGRADED","STALE"}: return "warning"
    return "neutral"

def build_operations_view(items: Sequence[Mapping[str,Any]]) -> dict[str,Any]:
    groups={"Krever handling":[],"Bør kontrolleres":[],"Normal drift":[]}
    for item in items:
        tone=severity_for(item); row=dict(item); row["tone"]=tone
        groups["Krever handling" if tone=="danger" else "Bør kontrolleres" if tone=="warning" else "Normal drift"].append(row)
    return {"groups":groups,"has_blockers":bool(groups["Krever handling"])}
