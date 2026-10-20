"""Offline staged-entry and sector-exposure research primitives.

No historical sector inferred from today's classification. No trades or state
mutations. Candidate policies are evaluated only with time-stamped inputs.
"""
from __future__ import annotations
from dataclasses import dataclass
from math import isfinite

@dataclass(frozen=True)
class Policy:
    initial_pct: float=1.0
    max_position_pct: float=5.0
    sector_limit_pct: float=25.0
    industry_limit_pct: float=15.0
    max_industry_names: int=4
    max_names: int=30
    minimum_names_target: int=20
    confirmation_days: tuple=(3,7,15)
    target_weights: tuple=(2.0,3.5,5.0)

def validate_policy(policy):
    if not 0.5<=policy.initial_pct<=2.0 or not policy.initial_pct<=policy.max_position_pct<=5.0:
        raise ValueError("Invalid initial/max weight")
    if not 0<policy.industry_limit_pct<=policy.sector_limit_pct<=100:
        raise ValueError("Invalid exposure caps")
    if not 20<=policy.max_names<=30 or not 0<policy.max_industry_names<=policy.max_names:
        raise ValueError("Invalid diversification limits")
    if len(policy.confirmation_days)!=len(policy.target_weights) or tuple(sorted(policy.confirmation_days))!=policy.confirmation_days:
        raise ValueError("Invalid stage chronology")
    if any(x<policy.initial_pct or x>policy.max_position_pct for x in policy.target_weights):
        raise ValueError("Invalid stage target")
    return policy

def next_target(policy, elapsed_sessions, *, confirmed):
    validate_policy(policy)
    target=policy.initial_pct
    if not confirmed:return target
    for age,weight in zip(policy.confirmation_days,policy.target_weights):
        if elapsed_sessions>=age:target=weight
    return min(target,policy.max_position_pct)

def permitted_weight(policy, positions, *, ticker, sector, industry, target_pct,
                     available_cash_pct=100.0):
    """Point-in-time portfolio weights; unknown sector/industry blocks additions."""
    validate_policy(policy)
    if not sector or not industry:return {"allowed_pct":0., "reason":"MISSING_AS_OF_CLASSIFICATION"}
    if not all(isfinite(float(x)) and float(x)>=0 for x in (target_pct,available_cash_pct)):
        raise ValueError("Invalid weights")
    present={x["ticker"]:x for x in positions}
    existing=present.get(ticker,{})
    current=float(existing.get("weight_pct") or 0)
    if not existing and len(present)>=policy.max_names:
        return {"allowed_pct":0., "reason":"MAX_NAMES"}
    same_sector=sum(float(x["weight_pct"]) for x in positions if x.get("sector")==sector)
    same_industry=sum(float(x["weight_pct"]) for x in positions if x.get("industry")==industry)
    industry_names=sum(1 for x in positions if x.get("industry")==industry and x.get("ticker")!=ticker)
    if not existing and industry_names>=policy.max_industry_names:
        return {"allowed_pct":0., "reason":"INDUSTRY_NAMES_CAP"}
    room=min(policy.max_position_pct-current,
             policy.sector_limit_pct-same_sector,
             policy.industry_limit_pct-same_industry,
             float(target_pct)-current,float(available_cash_pct))
    return {"allowed_pct":round(max(0.,room),6),
            "reason":"OK" if room>0 else "EXPOSURE_OR_CASH_CAP"}

def can_use_historical_snapshot(snapshot):
    """Require historical signals/classifications for defensible counterfactual replay."""
    if not isinstance(snapshot,dict) or not snapshot.get("as_of") or not snapshot.get("candidates"):
        return False
    return all(isinstance(row,dict) and row.get("signal_as_of") and row.get("sector_as_of")
               and row.get("sector") and row.get("industry") and row.get("industry_as_of")
               for row in snapshot["candidates"])
