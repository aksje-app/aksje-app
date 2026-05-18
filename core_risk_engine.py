"""
core_risk_engine.py

Consolidated Core Risk Engine for portfolio/fund analysis.

This module deliberately keeps the first hedge-fund-level step compact:
1) normalize portfolio/holdings data
2) infer factor exposures
3) build a dependency/factor graph
4) run deterministic stress scenarios
5) produce risk budgeting / attribution

No network calls. It can be used by fund/ETF rows, mixed portfolio rows, UI tests,
or later optimizer/validation layers.
"""

from __future__ import annotations
from utils import _safe_float, _now_iso, _clamp  # v18.6.3 centralized helpers

from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence, Tuple
import math

from app_version import get_app_version


CORE_RISK_SCHEMA_VERSION = 1

EQUITY_LIKE_TYPES = {"Aksje", "Fond", "ETF", "Aktivt fond", "Indeksfond", "Kombinasjonsfond"}
FIXED_INCOME_TYPES = {"Rente-/obligasjonsfond", "Pengemarkedsfond", "High yield-fond"}
TECH_SYMBOLS = {"AAPL", "MSFT", "NVDA", "GOOGL", "GOOG", "META", "AMZN", "TSLA", "AMD", "AVGO", "ORCL", "CRM", "ADBE", "NFLX"}
TECH_FUNDS = {"QQQ", "XLK", "ARKK", "ARKW", "JEPQ"}
BROAD_FUNDS = {"SPY", "VOO", "VTI", "DIA", "SCHB", "ITOT", "ACWI", "VT", "IUSQ.DE", "EUNL.DE", "VEA", "IEFA"}
CREDIT_FUNDS = {"HYG", "JNK", "ANGL", "HYLB", "USHY", "SJNK", "BKLN", "KRAFT_HIGH_YIELD_D", "LQD", "VCIT"}
DURATION_FUNDS = {"TLT", "IEF", "AGG", "BND", "LQD", "VCIT"}
CASH_LIKE_FUNDS = {"SGOV", "BIL", "SHV", "ICSH", "MINT"}

CANONICAL_FACTORS = [
    "equity_beta",
    "tech_ai",
    "duration",
    "credit_spread",
    "usd_fx",
    "liquidity",
    "concentration",
]


@dataclass(frozen=True)
class RiskNode:
    node_id: str
    node_type: str
    label: str
    weight_pct: float = 0.0
    metadata: Dict[str, Any] | None = None

    def as_dict(self) -> Dict[str, Any]:
        out = asdict(self)
        out["metadata"] = dict(self.metadata or {})
        return out








def _symbol(value: Any) -> str:
    return str(value or "").strip().upper().replace(" ", "")


def _infer_asset_type(row: Mapping[str, Any]) -> str:
    typ = str(row.get("asset_type") or row.get("fund_type") or "").strip()
    if typ:
        return typ
    s = _symbol(row.get("symbol") or row.get("ticker"))
    if s in CASH_LIKE_FUNDS:
        return "Pengemarkedsfond"
    if s in CREDIT_FUNDS:
        return "High yield-fond" if s in {"HYG", "JNK", "ANGL", "HYLB", "USHY", "SJNK", "BKLN", "KRAFT_HIGH_YIELD_D"} else "Rente-/obligasjonsfond"
    if s in DURATION_FUNDS:
        return "Rente-/obligasjonsfond"
    if s in TECH_FUNDS or s in BROAD_FUNDS:
        return "ETF"
    return "Aksje"


def normalize_risk_holdings(rows: Sequence[Mapping[str, Any]]) -> List[Dict[str, Any]]:
    """Normalize rows into holdings with explicit weights summing to 100."""
    normalized: List[Dict[str, Any]] = []
    for item in rows or []:
        r = dict(item or {})
        sym = _symbol(r.get("symbol") or r.get("ticker") or r.get("name"))
        if not sym:
            continue
        normalized.append({
            "symbol": sym,
            "name": str(r.get("name") or r.get("longName") or r.get("shortName") or sym),
            "asset_type": _infer_asset_type(r),
            "weight_pct": _safe_float(r.get("weight_pct"), None),
            "sector": str(r.get("sector") or (r.get("metadata") or {}).get("sector") or ""),
            "geography": str(r.get("geography") or (r.get("metadata") or {}).get("geography") or ""),
            "role": str(r.get("role") or r.get("recommended_role") or ""),
            "metadata": dict(r.get("metadata") or {}),
            "raw": r,
        })
    if not normalized:
        return []
    known_total = sum(float(x.get("weight_pct") or 0.0) for x in normalized if x.get("weight_pct") is not None)
    missing = [x for x in normalized if x.get("weight_pct") is None]
    if missing:
        remaining = max(0.0, 100.0 - known_total)
        fill = remaining / len(missing) if remaining > 0 else 100.0 / len(normalized)
        for x in missing:
            x["weight_pct"] = fill
    total = sum(float(x.get("weight_pct") or 0.0) for x in normalized) or 1.0
    for x in normalized:
        x["weight_pct"] = round(float(x.get("weight_pct") or 0.0) * 100.0 / total, 4)
    return normalized


def infer_factor_exposures(holding: Mapping[str, Any]) -> Dict[str, float]:
    """Infer 0-100 factor exposure vector from available static fields."""
    s = _symbol(holding.get("symbol"))
    typ = str(holding.get("asset_type") or "")
    sector = str(holding.get("sector") or "").lower()
    geo = str(holding.get("geography") or "").lower()
    role = str(holding.get("role") or "").lower()
    meta = dict(holding.get("metadata") or {})

    equity = 80.0 if typ in EQUITY_LIKE_TYPES else 15.0
    tech = 20.0 if typ in EQUITY_LIKE_TYPES else 5.0
    duration = 8.0
    credit = 8.0
    usd = 55.0
    liquidity = 30.0
    concentration = 25.0

    if s in TECH_SYMBOLS or s in TECH_FUNDS or "teknologi" in sector or "tech" in sector or "vekst" in sector:
        tech = 90.0
        equity = max(equity, 90.0)
        concentration = 45.0
    if s in BROAD_FUNDS or "bred" in sector or "grunnmur" in role:
        equity = max(equity, 75.0)
        tech = max(tech, 35.0)
        concentration = 15.0
        liquidity = 18.0
    if typ == "Aktivt fond":
        liquidity += 12.0
        concentration += 10.0
    if typ == "High yield-fond" or s in CREDIT_FUNDS:
        equity = 35.0
        credit = 90.0
        duration = 35.0
        liquidity = 45.0
    if typ == "Rente-/obligasjonsfond" or s in DURATION_FUNDS:
        equity = 10.0
        duration = 75.0 if s not in {"SHY", "BSV"} else 35.0
        credit = max(credit, 35.0 if s not in {"TLT", "IEF"} else 15.0)
        liquidity = 25.0
    if typ == "Pengemarkedsfond" or s in CASH_LIKE_FUNDS:
        equity = 2.0
        duration = 10.0
        credit = 8.0
        liquidity = 5.0
        tech = 0.0
        concentration = 5.0
    if "norge" in geo:
        usd = 10.0
    elif "europa" in geo or "sverige" in geo:
        usd = 25.0
    elif "global" in geo or "usa" in geo or not geo:
        usd = 55.0

    overrides = meta.get("factor_exposures") if isinstance(meta.get("factor_exposures"), Mapping) else {}
    exposures = {
        "equity_beta": equity,
        "tech_ai": tech,
        "duration": duration,
        "credit_spread": credit,
        "usd_fx": usd,
        "liquidity": liquidity,
        "concentration": concentration,
    }
    for key, value in dict(overrides or {}).items():
        if key in exposures:
            exposures[key] = _safe_float(value, exposures[key]) or exposures[key]
    return {k: round(_clamp(v), 2) for k, v in exposures.items()}


def build_factor_graph(rows: Sequence[Mapping[str, Any]]) -> Dict[str, Any]:
    holdings = normalize_risk_holdings(rows)
    nodes: List[Dict[str, Any]] = []
    edges: List[Dict[str, Any]] = []
    for factor in CANONICAL_FACTORS:
        nodes.append(RiskNode(f"factor:{factor}", "factor", factor.replace("_", " ").title()).as_dict())
    for h in holdings:
        h_id = f"holding:{h['symbol']}"
        nodes.append(RiskNode(h_id, "holding", h["symbol"], float(h.get("weight_pct") or 0.0), {"asset_type": h.get("asset_type")}).as_dict())
        exposures = infer_factor_exposures(h)
        for factor, exposure in exposures.items():
            if exposure <= 0:
                continue
            weighted = round(float(h.get("weight_pct") or 0.0) * exposure / 100.0, 4)
            edges.append({"source": h_id, "target": f"factor:{factor}", "exposure": exposure, "weighted_exposure": weighted})
    factor_totals: Dict[str, float] = {factor: 0.0 for factor in CANONICAL_FACTORS}
    for edge in edges:
        factor = str(edge["target"]).replace("factor:", "")
        factor_totals[factor] = round(factor_totals.get(factor, 0.0) + float(edge.get("weighted_exposure") or 0.0), 4)
    hidden_dependencies = [
        {"factor": k, "severity": "Høy" if v >= 55 else "Middels", "weighted_exposure": round(v, 2)}
        for k, v in factor_totals.items() if v >= 35
    ]
    hidden_dependencies.sort(key=lambda x: float(x.get("weighted_exposure") or 0.0), reverse=True)
    return {
        "model": "Core Risk Factor Graph",
        "schema_version": CORE_RISK_SCHEMA_VERSION,
        "holding_count": len(holdings),
        "nodes": nodes,
        "edges": edges,
        "factor_totals": {k: round(v, 2) for k, v in factor_totals.items()},
        "hidden_dependencies": hidden_dependencies,
        "summary": "Faktorgraph kobler beholdninger til felles risikofaktorer slik at overlapp måles på risiko, ikke bare ticker.",
    }


STRESS_SCENARIOS = {
    "equity_selloff": {"label": "Aksjefall", "shocks": {"equity_beta": -0.24, "tech_ai": -0.08, "liquidity": -0.03}},
    "tech_ai_selloff": {"label": "Tech/AI-selloff", "shocks": {"tech_ai": -0.32, "equity_beta": -0.10, "concentration": -0.04}},
    "rate_shock": {"label": "Rentehopp", "shocks": {"duration": -0.16, "equity_beta": -0.04, "credit_spread": -0.04}},
    "credit_stress": {"label": "Kredittstress", "shocks": {"credit_spread": -0.22, "liquidity": -0.06, "equity_beta": -0.06}},
    "usd_nok_down": {"label": "USD-svekkelse", "shocks": {"usd_fx": -0.10}},
    "liquidity_crunch": {"label": "Likviditetsskvis", "shocks": {"liquidity": -0.18, "concentration": -0.06, "credit_spread": -0.06}},
}


def run_stress_tests(rows: Sequence[Mapping[str, Any]], *, scenarios: Optional[Mapping[str, Mapping[str, Any]]] = None) -> Dict[str, Any]:
    holdings = normalize_risk_holdings(rows)
    scenario_def = dict(scenarios or STRESS_SCENARIOS)
    results: List[Dict[str, Any]] = []
    for key, scenario in scenario_def.items():
        shocks = dict(scenario.get("shocks") or {})
        contributions: List[Dict[str, Any]] = []
        impact = 0.0
        for h in holdings:
            exposures = infer_factor_exposures(h)
            h_impact = 0.0
            factor_hits: Dict[str, float] = {}
            for factor, shock in shocks.items():
                hit = float(h.get("weight_pct") or 0.0) * float(exposures.get(factor, 0.0)) / 100.0 * float(shock)
                h_impact += hit
                factor_hits[factor] = round(hit, 4)
            impact += h_impact
            if abs(h_impact) >= 0.05:
                contributions.append({"symbol": h.get("symbol"), "impact_pct": round(h_impact, 3), "factor_hits": factor_hits})
        contributions.sort(key=lambda x: abs(float(x.get("impact_pct") or 0.0)), reverse=True)
        severity = "Høy" if impact <= -12 else "Middels" if impact <= -6 else "Lav"
        results.append({
            "scenario": key,
            "label": scenario.get("label") or key,
            "estimated_impact_pct": round(impact, 2),
            "severity": severity,
            "top_contributors": contributions[:8],
        })
    results.sort(key=lambda x: float(x.get("estimated_impact_pct") or 0.0))
    return {
        "model": "Core Risk Stress Testing",
        "schema_version": CORE_RISK_SCHEMA_VERSION,
        "scenario_count": len(results),
        "worst_scenario": results[0] if results else None,
        "best_scenario": results[-1] if results else None,
        "scenarios": results,
        "summary": "Stressmotoren oversetter faktorgraph til estimert porteføljeeffekt per scenario.",
    }


def build_risk_budget(rows: Sequence[Mapping[str, Any]]) -> Dict[str, Any]:
    graph = build_factor_graph(rows)
    totals = dict(graph.get("factor_totals") or {})
    weights = {
        "equity_beta": 1.00,
        "tech_ai": 1.15,
        "duration": 0.80,
        "credit_spread": 1.05,
        "usd_fx": 0.45,
        "liquidity": 0.75,
        "concentration": 0.90,
    }
    raw = {k: max(0.0, float(v or 0.0)) * weights.get(k, 1.0) for k, v in totals.items()}
    denom = sum(raw.values()) or 1.0
    budget = {k: round(v * 100.0 / denom, 2) for k, v in raw.items()}
    top = sorted(({"factor": k, "risk_budget_pct": v, "weighted_exposure": round(float(totals.get(k, 0.0)), 2)} for k, v in budget.items()), key=lambda x: x["risk_budget_pct"], reverse=True)
    return {
        "model": "Core Risk Budget",
        "schema_version": CORE_RISK_SCHEMA_VERSION,
        "risk_budget": budget,
        "top_risk_factors": top[:7],
        "summary": "Risk budget viser hva som driver porteføljerisikoen etter eksponering og faktor-risikovekt.",
    }


def build_core_risk_profile(rows: Sequence[Mapping[str, Any]], *, selection_info: Optional[Mapping[str, Any]] = None) -> Dict[str, Any]:
    holdings = normalize_risk_holdings(rows)
    graph = build_factor_graph(holdings)
    stress = run_stress_tests(holdings)
    budget = build_risk_budget(holdings)
    worst = stress.get("worst_scenario") or {}
    top_factor = (budget.get("top_risk_factors") or [{}])[0]
    risk_score = 72.0
    if worst:
        risk_score += max(-35.0, min(10.0, float(worst.get("estimated_impact_pct") or 0.0)))
    if float((top_factor or {}).get("risk_budget_pct") or 0.0) >= 35:
        risk_score -= 8.0
    if len(graph.get("hidden_dependencies") or []) >= 3:
        risk_score -= 6.0
    risk_score = round(_clamp(risk_score), 1)
    return {
        "version": get_app_version(),
        "created_at": _now_iso(),
        "schema_version": CORE_RISK_SCHEMA_VERSION,
        "model": "Core Risk Engine",
        "status": "ok" if holdings else "empty",
        "selection_info": dict(selection_info or {}),
        "holding_count": len(holdings),
        "holdings": holdings,
        "factor_graph": graph,
        "stress_testing": stress,
        "risk_budgeting": budget,
        "core_risk_score": risk_score,
        "summary": f"Core Risk Engine samlet {len(holdings)} posisjoner, {len(graph.get('hidden_dependencies') or [])} tydelige faktoravhengigheter og worst-case scenario {worst.get('label') or 'ukjent'}.",
    }


__all__ = [
    "CORE_RISK_SCHEMA_VERSION",
    "CANONICAL_FACTORS",
    "STRESS_SCENARIOS",
    "normalize_risk_holdings",
    "infer_factor_exposures",
    "build_factor_graph",
    "run_stress_tests",
    "build_risk_budget",
    "build_core_risk_profile",
]
