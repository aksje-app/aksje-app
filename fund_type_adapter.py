"""
fund_type_adapter.py

Fund Type Adapter layer for the Portfolio Intelligence stack.

Purpose:
- keep one common hedge-fund-style engine for all fund types
- avoid forcing equity-style risk assumptions onto bond, money-market or alternative funds
- map each fund type to relevant factors, stress scenarios, optimizer constraints and validation priorities

This module is deterministic and does not fetch market data.
"""

from __future__ import annotations

from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from typing import Any, Dict, List, Mapping, Optional, Sequence

from app_version import get_app_version
from core_risk_engine import CANONICAL_FACTORS, build_core_risk_profile, run_stress_tests
from portfolio_intelligence_engine import PortfolioConstraints, build_portfolio_intelligence_profile
from validation_engine import build_validation_profile


FUND_TYPE_ADAPTER_SCHEMA_VERSION = 1


@dataclass(frozen=True)
class FundTypeProfile:
    fund_type: str
    canonical_type: str
    analysis_depth: str
    primary_factors: List[str]
    secondary_factors: List[str]
    stress_scenarios: Dict[str, Dict[str, Any]]
    optimizer_constraints: Dict[str, Any]
    regime_preferences: Dict[str, float]
    data_requirements: List[str]
    notes: List[str]

    def as_dict(self) -> Dict[str, Any]:
        return asdict(self)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _norm(value: Any) -> str:
    return str(value or "").strip().lower().replace("_", "-")


def _fund_type_from_row(row: Mapping[str, Any]) -> str:
    return str(row.get("fund_type") or row.get("asset_type") or row.get("category") or "Aksjefond").strip()


ALIASES: Dict[str, str] = {
    "aksje": "aksjefond",
    "aksjefond": "aksjefond",
    "equity": "aksjefond",
    "equity fund": "aksjefond",
    "fond": "aksjefond",
    "aktivt fond": "aksjefond",
    "indeks": "indeksfond",
    "indeksfond": "indeksfond",
    "index": "indeksfond",
    "index fund": "indeksfond",
    "etf": "indeksfond",
    "sektor": "sektorfond",
    "sektorfond": "sektorfond",
    "sector fund": "sektorfond",
    "global": "globalt fond",
    "globalt fond": "globalt fond",
    "global fund": "globalt fond",
    "kombinasjon": "kombinasjonsfond",
    "kombinasjonsfond": "kombinasjonsfond",
    "balanced": "kombinasjonsfond",
    "multi asset": "kombinasjonsfond",
    "rente": "rentefond",
    "rentefond": "rentefond",
    "rente-/obligasjonsfond": "rentefond",
    "obligasjon": "rentefond",
    "bond": "rentefond",
    "bond fund": "rentefond",
    "high yield": "high yield-fond",
    "high yield-fond": "high yield-fond",
    "kreditt": "high yield-fond",
    "credit": "high yield-fond",
    "pengemarked": "pengemarkedsfond",
    "pengemarkedsfond": "pengemarkedsfond",
    "money market": "pengemarkedsfond",
    "cash": "pengemarkedsfond",
    "hedgefond": "alternativt fond",
    "hedge fund": "alternativt fond",
    "alternativ": "alternativt fond",
    "alternatives": "alternativt fond",
    "alternativt fond": "alternativt fond",
}


def canonicalize_fund_type(fund_type: Any) -> str:
    key = _norm(fund_type)
    if key in ALIASES:
        return ALIASES[key]
    if "high" in key and "yield" in key:
        return "high yield-fond"
    if "money" in key or "pengemark" in key:
        return "pengemarkedsfond"
    if "oblig" in key or "bond" in key or "rente" in key:
        return "rentefond"
    if "sector" in key or "sektor" in key:
        return "sektorfond"
    if "index" in key or "indeks" in key or key == "etf":
        return "indeksfond"
    if "hedge" in key or "alternativ" in key:
        return "alternativt fond"
    if "komb" in key or "balanced" in key or "multi" in key:
        return "kombinasjonsfond"
    if "global" in key:
        return "globalt fond"
    return "aksjefond"


BASE_SCENARIOS: Dict[str, Dict[str, Any]] = {
    "equity_drawdown": {"label": "Aksjefall", "factor_shocks": {"equity_beta": -0.24, "tech_ai": -0.30, "liquidity": -0.06}},
    "tech_ai_selloff": {"label": "Tech/AI-selloff", "factor_shocks": {"tech_ai": -0.38, "equity_beta": -0.14, "concentration": -0.08}},
    "rate_shock": {"label": "Rentehopp", "factor_shocks": {"duration": -0.22, "credit_spread": -0.06}},
    "credit_spread_widening": {"label": "Spread-utgang", "factor_shocks": {"credit_spread": -0.26, "liquidity": -0.12, "equity_beta": -0.05}},
    "usd_nok_reversal": {"label": "USD/NOK-reversering", "factor_shocks": {"usd_fx": -0.12}},
    "liquidity_squeeze": {"label": "Likviditetsskvis", "factor_shocks": {"liquidity": -0.30, "credit_spread": -0.10, "concentration": -0.08}},
    "inflation_reacceleration": {"label": "Inflasjon opp igjen", "factor_shocks": {"duration": -0.16, "equity_beta": -0.08, "credit_spread": -0.06}},
}


PROFILE_LIBRARY: Dict[str, Dict[str, Any]] = {
    "aksjefond": {
        "analysis_depth": "full",
        "primary_factors": ["equity_beta", "tech_ai", "concentration"],
        "secondary_factors": ["usd_fx", "liquidity", "credit_spread"],
        "scenario_keys": ["equity_drawdown", "tech_ai_selloff", "usd_nok_reversal", "liquidity_squeeze"],
        "constraints": {"max_position_pct": 20.0, "max_turnover_pct": 35.0, "max_factor_budget_pct": 36.0, "target_position_count": 8},
        "regimes": {"balanced": 1.0, "risk_on": 1.08, "risk_off": 0.86, "growth": 1.05},
        "data_requirements": ["holdings", "sector", "geography", "top holdings", "equity beta proxy"],
        "notes": ["Best egnet for faktorgraph og overlap-analyse."],
    },
    "indeksfond": {
        "analysis_depth": "full",
        "primary_factors": ["equity_beta", "usd_fx", "tech_ai"],
        "secondary_factors": ["concentration", "liquidity"],
        "scenario_keys": ["equity_drawdown", "tech_ai_selloff", "usd_nok_reversal"],
        "constraints": {"max_position_pct": 25.0, "max_turnover_pct": 25.0, "max_factor_budget_pct": 40.0, "target_position_count": 6},
        "regimes": {"balanced": 1.0, "risk_on": 1.04, "risk_off": 0.92},
        "data_requirements": ["index exposure", "geography", "sector weights", "currency"],
        "notes": ["God presisjon selv med aggregerte indeksdata."],
    },
    "sektorfond": {
        "analysis_depth": "full",
        "primary_factors": ["concentration", "tech_ai", "equity_beta"],
        "secondary_factors": ["liquidity", "usd_fx"],
        "scenario_keys": ["equity_drawdown", "tech_ai_selloff", "liquidity_squeeze", "usd_nok_reversal"],
        "constraints": {"max_position_pct": 15.0, "max_turnover_pct": 40.0, "max_factor_budget_pct": 32.0, "target_position_count": 8},
        "regimes": {"balanced": 1.0, "risk_on": 1.06, "risk_off": 0.80, "growth": 1.05},
        "data_requirements": ["sector", "top holdings", "concentration", "liquidity"],
        "notes": ["Krever strengere konsentrasjons- og regimekontroll."],
    },
    "globalt fond": {
        "analysis_depth": "full",
        "primary_factors": ["equity_beta", "usd_fx", "tech_ai"],
        "secondary_factors": ["concentration", "liquidity"],
        "scenario_keys": ["equity_drawdown", "usd_nok_reversal", "tech_ai_selloff"],
        "constraints": {"max_position_pct": 22.0, "max_turnover_pct": 32.0, "max_factor_budget_pct": 36.0, "target_position_count": 8},
        "regimes": {"balanced": 1.0, "risk_on": 1.04, "risk_off": 0.88},
        "data_requirements": ["geography", "currency", "sector", "top holdings"],
        "notes": ["Valuta og geografi må vektlegges høyere enn for rene Norge-fond."],
    },
    "kombinasjonsfond": {
        "analysis_depth": "full",
        "primary_factors": ["equity_beta", "duration", "credit_spread"],
        "secondary_factors": ["usd_fx", "liquidity", "concentration"],
        "scenario_keys": ["equity_drawdown", "rate_shock", "credit_spread_widening", "inflation_reacceleration"],
        "constraints": {"max_position_pct": 25.0, "max_turnover_pct": 30.0, "max_factor_budget_pct": 34.0, "target_position_count": 7},
        "regimes": {"balanced": 1.0, "risk_off": 0.96, "rate_shock": 0.88, "credit_stress": 0.90},
        "data_requirements": ["equity share", "duration", "credit quality", "currency"],
        "notes": ["Bør analyseres som multi-asset, ikke som vanlig aksjefond."],
    },
    "rentefond": {
        "analysis_depth": "conditional_full",
        "primary_factors": ["duration", "credit_spread", "liquidity"],
        "secondary_factors": ["usd_fx", "equity_beta"],
        "scenario_keys": ["rate_shock", "credit_spread_widening", "inflation_reacceleration", "liquidity_squeeze"],
        "constraints": {"max_position_pct": 30.0, "max_turnover_pct": 22.0, "max_factor_budget_pct": 30.0, "target_position_count": 6},
        "regimes": {"balanced": 1.0, "risk_off": 1.02, "rate_shock": 0.82, "credit_stress": 0.88},
        "data_requirements": ["duration", "yield", "credit quality", "spread duration", "liquidity"],
        "notes": ["Full presisjon krever duration og kredittdata."],
    },
    "high yield-fond": {
        "analysis_depth": "conditional_full",
        "primary_factors": ["credit_spread", "liquidity", "equity_beta"],
        "secondary_factors": ["duration", "usd_fx", "concentration"],
        "scenario_keys": ["credit_spread_widening", "liquidity_squeeze", "equity_drawdown", "rate_shock"],
        "constraints": {"max_position_pct": 18.0, "max_turnover_pct": 28.0, "max_factor_budget_pct": 24.0, "target_position_count": 8},
        "regimes": {"balanced": 1.0, "risk_on": 1.04, "risk_off": 0.78, "credit_stress": 0.72},
        "data_requirements": ["credit quality", "spread duration", "issuer concentration", "liquidity"],
        "notes": ["Skal behandles mer som kredittbeta enn trygg renteeksponering."],
    },
    "pengemarkedsfond": {
        "analysis_depth": "limited",
        "primary_factors": ["liquidity", "duration", "credit_spread"],
        "secondary_factors": ["usd_fx"],
        "scenario_keys": ["rate_shock", "liquidity_squeeze"],
        "constraints": {"max_position_pct": 35.0, "max_turnover_pct": 12.0, "max_factor_budget_pct": 22.0, "target_position_count": 4},
        "regimes": {"balanced": 1.0, "risk_off": 1.05, "rate_shock": 0.96},
        "data_requirements": ["maturity", "credit quality", "liquidity", "currency"],
        "notes": ["Mest relevant for likviditet, kort rente og kredittkvalitet."],
    },
    "alternativt fond": {
        "analysis_depth": "partial",
        "primary_factors": ["liquidity", "concentration", "equity_beta"],
        "secondary_factors": ["credit_spread", "duration", "usd_fx"],
        "scenario_keys": ["liquidity_squeeze", "equity_drawdown", "credit_spread_widening"],
        "constraints": {"max_position_pct": 12.0, "max_turnover_pct": 20.0, "max_factor_budget_pct": 24.0, "target_position_count": 8},
        "regimes": {"balanced": 1.0, "risk_on": 0.98, "risk_off": 0.86, "credit_stress": 0.84},
        "data_requirements": ["strategy", "leverage", "liquidity terms", "gross/net exposure", "correlation proxy"],
        "notes": ["Delvis analyse uten strategi-, leverage- og likviditetsdata."],
    },
}


def get_fund_type_profile(fund_type: Any) -> Dict[str, Any]:
    canonical = canonicalize_fund_type(fund_type)
    cfg = dict(PROFILE_LIBRARY.get(canonical) or PROFILE_LIBRARY["aksjefond"])
    scenarios = {k: BASE_SCENARIOS[k] for k in cfg["scenario_keys"] if k in BASE_SCENARIOS}
    profile = FundTypeProfile(
        fund_type=str(fund_type or canonical),
        canonical_type=canonical,
        analysis_depth=str(cfg["analysis_depth"]),
        primary_factors=list(cfg["primary_factors"]),
        secondary_factors=list(cfg["secondary_factors"]),
        stress_scenarios=scenarios,
        optimizer_constraints=dict(cfg["constraints"]),
        regime_preferences=dict(cfg["regimes"]),
        data_requirements=list(cfg["data_requirements"]),
        notes=list(cfg["notes"]),
    )
    return profile.as_dict()


def build_fund_type_adapter(rows: Sequence[Mapping[str, Any]]) -> Dict[str, Any]:
    buckets: Dict[str, Dict[str, Any]] = {}
    for row in rows or []:
        profile = get_fund_type_profile(_fund_type_from_row(row))
        key = profile["canonical_type"]
        if key not in buckets:
            buckets[key] = {"profile": profile, "count": 0, "symbols": []}
        buckets[key]["count"] += 1
        sym = str(row.get("symbol") or row.get("ticker") or row.get("name") or "").strip()
        if sym:
            buckets[key]["symbols"].append(sym.upper())

    primary = sorted(buckets.values(), key=lambda x: x["count"], reverse=True)[0]["profile"] if buckets else get_fund_type_profile("aksjefond")
    all_primary = []
    all_secondary = []
    scenario_keys = []
    requirements = []
    notes = []
    for item in buckets.values():
        p = item["profile"]
        all_primary.extend(p["primary_factors"])
        all_secondary.extend(p["secondary_factors"])
        scenario_keys.extend(p["stress_scenarios"].keys())
        requirements.extend(p["data_requirements"])
        notes.extend(p["notes"])

    return {
        "schema_version": FUND_TYPE_ADAPTER_SCHEMA_VERSION,
        "generated_at": _now_iso(),
        "app_version": get_app_version(),
        "primary_profile": primary,
        "fund_type_buckets": buckets,
        "combined_primary_factors": sorted(set(all_primary), key=CANONICAL_FACTORS.index),
        "combined_secondary_factors": sorted(set(all_secondary), key=CANONICAL_FACTORS.index),
        "combined_stress_scenarios": {k: BASE_SCENARIOS[k] for k in sorted(set(scenario_keys)) if k in BASE_SCENARIOS},
        "combined_data_requirements": sorted(set(requirements)),
        "combined_notes": sorted(set(notes)),
    }


def adapt_rows_for_fund_type(rows: Sequence[Mapping[str, Any]]) -> List[Dict[str, Any]]:
    """Add adapter metadata without mutating input rows."""
    adapted: List[Dict[str, Any]] = []
    for row in rows or []:
        r = dict(row or {})
        profile = get_fund_type_profile(_fund_type_from_row(r))
        meta = dict(r.get("metadata") or {})
        meta["fund_type_adapter"] = {
            "canonical_type": profile["canonical_type"],
            "analysis_depth": profile["analysis_depth"],
            "primary_factors": profile["primary_factors"],
            "secondary_factors": profile["secondary_factors"],
        }
        r["metadata"] = meta
        r["fund_type"] = profile["canonical_type"]
        adapted.append(r)
    return adapted


def build_fund_type_aware_analysis(
    rows: Sequence[Mapping[str, Any]],
    *,
    regime: str = "balanced",
    snapshots: Optional[Sequence[Any]] = None,
) -> Dict[str, Any]:
    adapter = build_fund_type_adapter(rows)
    adapted_rows = adapt_rows_for_fund_type(rows)
    primary_constraints = adapter["primary_profile"]["optimizer_constraints"]
    primary_scenarios = adapter["combined_stress_scenarios"] or adapter["primary_profile"]["stress_scenarios"]

    core = build_core_risk_profile(adapted_rows, selection_info={"fund_type_adapter": adapter["primary_profile"]})
    stress = run_stress_tests(adapted_rows, scenarios=primary_scenarios)
    intelligence = build_portfolio_intelligence_profile(
        adapted_rows,
        regime=regime,
        constraints=PortfolioConstraints(**primary_constraints),
    )
    validation = build_validation_profile(adapted_rows, snapshots=snapshots, regime=regime, constraints=primary_constraints)

    return {
        "schema_version": FUND_TYPE_ADAPTER_SCHEMA_VERSION,
        "generated_at": _now_iso(),
        "app_version": get_app_version(),
        "adapter": adapter,
        "adapted_rows": adapted_rows,
        "core_risk": core,
        "fund_type_stress": stress,
        "portfolio_intelligence": intelligence,
        "validation": validation,
    }
