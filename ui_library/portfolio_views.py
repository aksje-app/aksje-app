from __future__ import annotations
from typing import Any,Mapping

def position_age_view(position: Mapping[str,Any]) -> Mapping[str,Any]:
    return {"age_trading_days":position.get("holding_trading_days","unknown"),"reason":str(position.get("decision_reason") or position.get("reason") or "Ingen begrunnelse registrert")}

def build_portfolio_view(state: Mapping[str,Any]) -> dict[str,Any]:
    raw=state.get("positions") or {}
    rows=list(raw.values()) if isinstance(raw,Mapping) else list(raw)
    positions=[]
    for row in rows:
        item=dict(row); item.update(position_age_view(row)); positions.append(item)
    try: cash=f"{float(state.get('cash_pct') or 0):.1f}%"
    except (TypeError,ValueError): cash="-"
    changes=state.get("last_changes") or []
    groups={"new":[],"changed":[],"unchanged":[]}
    for change in changes:
        kind=str(change.get("kind") or change.get("change_kind") or "unchanged").lower()
        groups[kind if kind in groups else "changed"].append(change)
    return {"cash":{"label":"Kontantandel","value":cash},"positions":positions,"updated_at":str(state.get("updated_at") or ""),"changes":groups}
