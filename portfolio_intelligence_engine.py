"""
portfolio_intelligence_engine.py

Layer 2 after Core Risk Engine.

This module intentionally merges three hedge-fund-style capabilities into one
explainable engine:
1) optimizer-style candidate scoring and target weights
2) risk budgeting with factor-level limits
3) adaptive regime weights

The engine is deterministic, dependency-light and safe to call from tests, UI,
API routes or batch jobs. It does not fetch market data; it consumes rows that
can already include scores, weights, factor exposures and metadata.
"""

from __future__ import annotations
from utils import _safe_float, _now_iso, _clamp  # v18.6.3 centralized helpers

from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple
import math

from app_version import get_app_version
from core_risk_engine import CANONICAL_FACTORS, build_core_risk_profile, infer_factor_exposures


PORTFOLIO_INTELLIGENCE_SCHEMA_VERSION = 2


@dataclass(frozen=True)
class PortfolioConstraints:
    max_position_pct: float = 25.0
    min_position_pct: float = 0.0
    max_turnover_pct: float = 35.0
    max_factor_budget_pct: float = 35.0
    target_position_count: int = 8
    allow_short: bool = False

    def as_dict(self) -> Dict[str, Any]:
        return asdict(self)


REGIME_PRESETS: Dict[str, Dict[str, Any]] = {
    "balanced": {
        "label": "Balansert",
        "alpha_weight": 0.46,
        "risk_weight": 0.24,
        "stress_weight": 0.18,
        "diversification_weight": 0.12,
        "factor_tilts": {},
        "factor_caps": {},
    },
    "risk_on": {
        "label": "Risk-on / vekst",
        "alpha_weight": 0.58,
        "risk_weight": 0.16,
        "stress_weight": 0.12,
        "diversification_weight": 0.14,
        "factor_tilts": {"equity_beta": 0.08, "tech_ai": 0.06, "liquidity": -0.02},
        "factor_caps": {"concentration": 36.0},
    },
    "risk_off": {
        "label": "Risk-off",
        "alpha_weight": 0.34,
        "risk_weight": 0.32,
        "stress_weight": 0.24,
        "diversification_weight": 0.10,
        "factor_tilts": {"equity_beta": -0.10, "tech_ai": -0.10, "credit_spread": -0.08, "duration": 0.02},
        "factor_caps": {"equity_beta": 30.0, "tech_ai": 24.0, "credit_spread": 22.0},
    },
    "rate_shock": {
        "label": "Rentehopp",
        "alpha_weight": 0.36,
        "risk_weight": 0.30,
        "stress_weight": 0.24,
        "diversification_weight": 0.10,
        "factor_tilts": {"duration": -0.12, "credit_spread": -0.04, "liquidity": 0.02},
        "factor_caps": {"duration": 20.0, "credit_spread": 25.0},
    },
    "credit_stress": {
        "label": "Kredittstress",
        "alpha_weight": 0.34,
        "risk_weight": 0.31,
        "stress_weight": 0.25,
        "diversification_weight": 0.10,
        "factor_tilts": {"credit_spread": -0.14, "liquidity": 0.04, "equity_beta": -0.04},
        "factor_caps": {"credit_spread": 18.0, "liquidity": 28.0},
    },
    "growth": {
        "label": "Vekst",
        "alpha_weight": 0.56,
        "risk_weight": 0.17,
        "stress_weight": 0.13,
        "diversification_weight": 0.14,
        "factor_tilts": {"equity_beta": 0.06, "tech_ai": 0.08},
        "factor_caps": {"tech_ai": 38.0, "concentration": 35.0},
    },
}








def _as_constraints(value: Optional[Mapping[str, Any] | PortfolioConstraints]) -> PortfolioConstraints:
    if isinstance(value, PortfolioConstraints):
        return value
    data = dict(value or {})
    return PortfolioConstraints(
        max_position_pct=_safe_float(data.get("max_position_pct"), 25.0),
        min_position_pct=_safe_float(data.get("min_position_pct"), 0.0),
        max_turnover_pct=_safe_float(data.get("max_turnover_pct"), 35.0),
        max_factor_budget_pct=_safe_float(data.get("max_factor_budget_pct"), 35.0),
        target_position_count=int(_safe_float(data.get("target_position_count"), 8.0) or 8),
        allow_short=bool(data.get("allow_short", False)),
    )


def _regime_config(regime: str) -> Tuple[str, Dict[str, Any]]:
    key = str(regime or "balanced").strip().lower()
    if key not in REGIME_PRESETS:
        key = "balanced"
    return key, dict(REGIME_PRESETS[key])


def _row_alpha_score(raw: Mapping[str, Any]) -> float:
    for key in (
        "foundation_score",
        "portfolio_fit_score",
        "composite_score",
        "score",
        "ai_score",
        "rank_score",
    ):
        if key in raw:
            return _clamp(_safe_float(raw.get(key), 65.0))
    return 65.0


def _risk_penalty_from_exposures(exposures: Mapping[str, float]) -> float:
    weights = {
        "equity_beta": 0.22,
        "tech_ai": 0.18,
        "duration": 0.14,
        "credit_spread": 0.18,
        "usd_fx": 0.08,
        "liquidity": 0.10,
        "concentration": 0.10,
    }
    return sum(float(exposures.get(k, 0.0)) * w for k, w in weights.items())


def _worst_case_holding_stress(core: Mapping[str, Any], symbol: str) -> float:
    worst = 0.0
    for scenario in ((core.get("stress_testing") or {}).get("scenarios") or []):
        for item in scenario.get("top_contributors") or []:
            if str(item.get("symbol") or "").upper() == str(symbol or "").upper():
                worst = min(worst, _safe_float(item.get("impact_pct"), 0.0))
    return abs(worst)


def _diversification_score(exposures: Mapping[str, float]) -> float:
    vals = [float(exposures.get(k, 0.0)) for k in CANONICAL_FACTORS]
    if not vals:
        return 50.0
    max_exposure = max(vals)
    average = sum(vals) / len(vals)
    # Reward less single-factor dependence, but do not punish normal broad equity too hard.
    return _clamp(100.0 - (max_exposure - average) * 0.85)


def score_candidate(holding: Mapping[str, Any], core: Mapping[str, Any], regime_cfg: Mapping[str, Any]) -> Dict[str, Any]:
    raw = dict(holding.get("raw") or {})
    symbol = str(holding.get("symbol") or "")
    exposures = infer_factor_exposures(holding)
    alpha = _row_alpha_score(raw)
    risk_penalty = _risk_penalty_from_exposures(exposures)
    stress_penalty = _worst_case_holding_stress(core, symbol) * 4.0
    diversification = _diversification_score(exposures)

    regime_adjustment = 0.0
    for factor, tilt in dict(regime_cfg.get("factor_tilts") or {}).items():
        regime_adjustment += float(exposures.get(factor, 0.0)) * float(tilt)

    alpha_w = float(regime_cfg.get("alpha_weight", 0.46))
    risk_w = float(regime_cfg.get("risk_weight", 0.24))
    stress_w = float(regime_cfg.get("stress_weight", 0.18))
    div_w = float(regime_cfg.get("diversification_weight", 0.12))

    final = (
        alpha * alpha_w
        + (100.0 - risk_penalty) * risk_w
        + (100.0 - stress_penalty) * stress_w
        + diversification * div_w
        + regime_adjustment
    )

    return {
        "symbol": symbol,
        "name": holding.get("name") or symbol,
        "current_weight_pct": round(_safe_float(holding.get("weight_pct"), 0.0), 4),
        "alpha_score": round(alpha, 2),
        "risk_penalty": round(risk_penalty, 2),
        "stress_penalty": round(stress_penalty, 2),
        "diversification_score": round(diversification, 2),
        "regime_adjustment": round(regime_adjustment, 2),
        "suggested_score": round(_clamp(final), 2),
        "factor_exposures": exposures,
    }


def _initial_target_weights(candidates: List[Dict[str, Any]], constraints: PortfolioConstraints) -> List[Dict[str, Any]]:
    selected = list(candidates[: max(1, constraints.target_position_count)])
    floor = max(0.0, constraints.min_position_pct)
    cap = max(floor, constraints.max_position_pct)
    raw_scores = [max(0.0, float(c.get("suggested_score") or 0.0) - 35.0) for c in selected]
    denom = sum(raw_scores) or 1.0
    for c, raw in zip(selected, raw_scores):
        c["target_weight_pct"] = round(_clamp(raw * 100.0 / denom, floor, cap), 4)
    return _renormalize_targets(selected, cap=cap, floor=floor)


def _renormalize_targets(candidates: List[Dict[str, Any]], *, cap: float, floor: float) -> List[Dict[str, Any]]:
    if not candidates:
        return []
    for _ in range(8):
        total = sum(float(c.get("target_weight_pct") or 0.0) for c in candidates)
        if total <= 0:
            equal = 100.0 / len(candidates)
            for c in candidates:
                c["target_weight_pct"] = round(_clamp(equal, floor, cap), 4)
            continue
        scale = 100.0 / total
        for c in candidates:
            c["target_weight_pct"] = round(_clamp(float(c.get("target_weight_pct") or 0.0) * scale, floor, cap), 4)
        if abs(sum(float(c.get("target_weight_pct") or 0.0) for c in candidates) - 100.0) < 0.05:
            break
    total = sum(float(c.get("target_weight_pct") or 0.0) for c in candidates) or 1.0
    for c in candidates:
        c["target_weight_pct"] = round(float(c.get("target_weight_pct") or 0.0) * 100.0 / total, 4)
    return candidates


def _portfolio_factor_totals(candidates: Sequence[Mapping[str, Any]], weight_key: str = "target_weight_pct") -> Dict[str, float]:
    totals = {k: 0.0 for k in CANONICAL_FACTORS}
    for c in candidates:
        w = _safe_float(c.get(weight_key), 0.0)
        exposures = dict(c.get("factor_exposures") or {})
        for factor in CANONICAL_FACTORS:
            totals[factor] += w * _safe_float(exposures.get(factor), 0.0) / 100.0
    return {k: round(v, 2) for k, v in totals.items()}


def _factor_cap_breaches(totals: Mapping[str, float], constraints: PortfolioConstraints, regime_cfg: Mapping[str, Any]) -> List[Dict[str, Any]]:
    caps = {factor: constraints.max_factor_budget_pct for factor in CANONICAL_FACTORS}
    caps.update({k: _safe_float(v, constraints.max_factor_budget_pct) for k, v in dict(regime_cfg.get("factor_caps") or {}).items()})
    breaches = []
    for factor, value in totals.items():
        cap = caps.get(factor, constraints.max_factor_budget_pct)
        if float(value) > float(cap):
            breaches.append({"factor": factor, "value_pct": round(float(value), 2), "cap_pct": round(float(cap), 2), "excess_pct": round(float(value) - float(cap), 2)})
    breaches.sort(key=lambda x: x["excess_pct"], reverse=True)
    return breaches


def optimize_target_weights(candidates: List[Dict[str, Any]], constraints: PortfolioConstraints, regime_cfg: Mapping[str, Any]) -> Dict[str, Any]:
    ranked = sorted((dict(c) for c in candidates), key=lambda x: float(x.get("suggested_score") or 0.0), reverse=True)
    selected = _initial_target_weights(ranked, constraints)
    totals = _portfolio_factor_totals(selected)
    breaches = _factor_cap_breaches(totals, constraints, regime_cfg)

    # Small deterministic risk-budget pass: trim names most exposed to breached factors,
    # then redistribute to less exposed selected names.
    for breach in breaches[:3]:
        factor = breach["factor"]
        excess = float(breach["excess_pct"])
        if excess <= 0 or not selected:
            continue
        high = sorted(selected, key=lambda c: _safe_float((c.get("factor_exposures") or {}).get(factor), 0.0), reverse=True)
        low = sorted(selected, key=lambda c: _safe_float((c.get("factor_exposures") or {}).get(factor), 0.0))
        trim_budget = min(excess * 0.6, 8.0)
        trimmed = 0.0
        for c in high[: max(1, len(high) // 2)]:
            can_trim = max(0.0, _safe_float(c.get("target_weight_pct"), 0.0) - constraints.min_position_pct)
            trim = min(can_trim, trim_budget - trimmed, 2.5)
            if trim <= 0:
                continue
            c["target_weight_pct"] = round(_safe_float(c.get("target_weight_pct"), 0.0) - trim, 4)
            trimmed += trim
            if trimmed >= trim_budget:
                break
        if trimmed > 0:
            receivers = low[: max(1, len(low) // 2)]
            per = trimmed / len(receivers)
            for c in receivers:
                c["target_weight_pct"] = round(_safe_float(c.get("target_weight_pct"), 0.0) + per, 4)
        selected = _renormalize_targets(selected, cap=constraints.max_position_pct, floor=constraints.min_position_pct)
        totals = _portfolio_factor_totals(selected)
        breaches = _factor_cap_breaches(totals, constraints, regime_cfg)

    for c in selected:
        delta = _safe_float(c.get("target_weight_pct"), 0.0) - _safe_float(c.get("current_weight_pct"), 0.0)
        c["trade_delta_pct"] = round(delta, 4)
        c["action"] = "increase" if delta > 1.0 else "reduce" if delta < -1.0 else "hold"

    turnover = round(sum(abs(_safe_float(c.get("trade_delta_pct"), 0.0)) for c in selected) / 2.0, 2)
    if turnover > constraints.max_turnover_pct:
        # Blend toward current weights when turnover is above the constraint.
        blend = max(0.0, min(1.0, constraints.max_turnover_pct / turnover))
        for c in selected:
            target = _safe_float(c.get("target_weight_pct"), 0.0)
            current = _safe_float(c.get("current_weight_pct"), 0.0)
            c["target_weight_pct"] = round(current + (target - current) * blend, 4)
        selected = _renormalize_targets(selected, cap=constraints.max_position_pct, floor=constraints.min_position_pct)
        for c in selected:
            delta = _safe_float(c.get("target_weight_pct"), 0.0) - _safe_float(c.get("current_weight_pct"), 0.0)
            c["trade_delta_pct"] = round(delta, 4)
            c["action"] = "increase" if delta > 1.0 else "reduce" if delta < -1.0 else "hold"
        turnover = round(sum(abs(_safe_float(c.get("trade_delta_pct"), 0.0)) for c in selected) / 2.0, 2)

    final_totals = _portfolio_factor_totals(selected)
    final_breaches = _factor_cap_breaches(final_totals, constraints, regime_cfg)
    return {
        "model": "Portfolio Optimizer",
        "selected_count": len(selected),
        "target_weights": selected,
        "portfolio_factor_totals": final_totals,
        "factor_cap_breaches": final_breaches,
        "estimated_turnover_pct": turnover,
        "constraint_status": "breach" if final_breaches or turnover > constraints.max_turnover_pct + 0.01 else "ok",
    }


def build_risk_budget_policy(core: Mapping[str, Any], optimizer_result: Mapping[str, Any], constraints: PortfolioConstraints, regime_cfg: Mapping[str, Any]) -> Dict[str, Any]:
    current = dict(((core.get("risk_budgeting") or {}).get("risk_budget") or {}))
    target_factor_totals = dict(optimizer_result.get("portfolio_factor_totals") or {})
    breaches = list(optimizer_result.get("factor_cap_breaches") or [])
    guidance = []
    for breach in breaches:
        factor = breach.get("factor")
        guidance.append({
            "factor": factor,
            "message": f"Reduser {factor} med ca. {breach.get('excess_pct')} prosentpoeng for å komme under regime-/risikocap.",
            "priority": "high" if _safe_float(breach.get("excess_pct"), 0.0) >= 5 else "medium",
        })
    if not guidance:
        guidance.append({"factor": "overall", "message": "Target-porteføljen ligger innenfor aktive factor caps.", "priority": "low"})
    return {
        "model": "Risk Budget Policy",
        "current_risk_budget_pct": current,
        "target_factor_exposure_pct": target_factor_totals,
        "max_factor_budget_pct": constraints.max_factor_budget_pct,
        "regime_factor_caps": dict(regime_cfg.get("factor_caps") or {}),
        "guidance": guidance,
    }


def build_portfolio_intelligence_profile(
    rows: Sequence[Mapping[str, Any]],
    *,
    regime: str = "balanced",
    constraints: Optional[Mapping[str, Any] | PortfolioConstraints] = None,
    selection_info: Optional[Mapping[str, Any]] = None,
) -> Dict[str, Any]:
    """Build a full Portfolio Intelligence profile from portfolio/fund rows."""
    regime_key, regime_cfg = _regime_config(regime)
    constraints_obj = _as_constraints(constraints)
    core = build_core_risk_profile(rows, selection_info=selection_info)

    candidates = [score_candidate(h, core, regime_cfg) for h in core.get("holdings") or []]
    candidates.sort(key=lambda x: x["suggested_score"], reverse=True)
    optimizer = optimize_target_weights(candidates, constraints_obj, regime_cfg)
    budget_policy = build_risk_budget_policy(core, optimizer, constraints_obj, regime_cfg)

    warnings: List[str] = []
    worst = (core.get("stress_testing") or {}).get("worst_scenario") or {}
    if _safe_float(worst.get("estimated_impact_pct"), 0.0) <= -10.0:
        warnings.append(f"Worst-case stress er høy: {worst.get('label')} {worst.get('estimated_impact_pct')}%.")
    if optimizer.get("constraint_status") != "ok":
        warnings.append("Optimizer fant gjenværende factor/turnover-brudd som bør vurderes manuelt.")

    return {
        "version": get_app_version(),
        "created_at": _now_iso(),
        "schema_version": PORTFOLIO_INTELLIGENCE_SCHEMA_VERSION,
        "model": "Portfolio Intelligence Engine",
        "status": "ok" if candidates else "empty",
        "regime": regime_key,
        "regime_config": regime_cfg,
        "constraints": constraints_obj.as_dict(),
        "core_risk_engine": core,
        "ranked_candidates": candidates,
        "optimizer": optimizer,
        "risk_budget_policy": budget_policy,
        "warnings": warnings,
        "summary": "Samler optimizer, risk budgeting og adaptive regimevekter i ett forklarbart porteføljelag etter Core Risk Engine.",
    }


__all__ = [
    "PORTFOLIO_INTELLIGENCE_SCHEMA_VERSION",
    "PortfolioConstraints",
    "REGIME_PRESETS",
    "score_candidate",
    "optimize_target_weights",
    "build_risk_budget_policy",
    "build_portfolio_intelligence_profile",
]
