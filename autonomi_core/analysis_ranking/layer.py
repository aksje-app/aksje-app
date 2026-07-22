"""Explainable, sector-aware parallel strategy lenses for Autonomy v18.8.8."""
from __future__ import annotations

import math
from dataclasses import dataclass, asdict
from typing import Any, Mapping


LAYER_VERSION = "v18.8.8"
STRATEGIES = ("Quality", "Growth", "Value", "Income", "Insider", "Momentum", "Event Recovery")

SECTOR_ALIASES = {
    "technology": "Technology", "teknologi": "Technology",
    "financial services": "Financials", "financial": "Financials", "finans": "Financials",
    "energy": "Energy", "energi": "Energy", "oil & gas": "Energy",
    "healthcare": "Healthcare", "helse": "Healthcare",
    "industrials": "Industrials", "industri": "Industrials",
    "consumer defensive": "Consumer", "consumer cyclical": "Consumer", "forbruksvarer": "Consumer",
    "real estate": "Real Estate", "eiendom": "Real Estate",
    "utilities": "Utilities", "forsyning": "Utilities",
    "communication services": "Communication", "kommunikasjon": "Communication",
    "basic materials": "Materials", "materialer": "Materials",
}

SECTOR_BENCHMARKS = {
    "Technology": {"pe_anchor": 28, "growth_good": 30, "yield_good": 2.5},
    "Financials": {"pe_anchor": 14, "growth_good": 15, "yield_good": 5.0},
    "Energy": {"pe_anchor": 12, "growth_good": 12, "yield_good": 7.0},
    "Healthcare": {"pe_anchor": 25, "growth_good": 22, "yield_good": 3.0},
    "Industrials": {"pe_anchor": 19, "growth_good": 18, "yield_good": 4.0},
    "Consumer": {"pe_anchor": 20, "growth_good": 18, "yield_good": 4.0},
    "Real Estate": {"pe_anchor": 18, "growth_good": 12, "yield_good": 7.0},
    "Utilities": {"pe_anchor": 17, "growth_good": 10, "yield_good": 6.0},
    "Communication": {"pe_anchor": 21, "growth_good": 20, "yield_good": 4.0},
    "Materials": {"pe_anchor": 15, "growth_good": 14, "yield_good": 5.0},
    "Unknown": {"pe_anchor": 18, "growth_good": 20, "yield_good": 5.0},
}

STRATEGY_WEIGHTS = {
    "Quality": {"fundamental": .40, "risk_adjusted": .20, "valuation": .15, "sentiment": .15, "sector_context": .10},
    "Growth": {"growth": .35, "technical": .20, "fundamental": .15, "valuation": .05, "sentiment": .15, "sector_context": .10},
    "Value": {"valuation": .40, "fundamental": .25, "risk_adjusted": .15, "insider": .10, "sector_context": .10},
    "Income": {"income": .40, "fundamental": .20, "risk_adjusted": .20, "valuation": .10, "sector_context": .10},
    "Insider": {"insider": .45, "valuation": .15, "fundamental": .20, "sentiment": .10, "sector_context": .10},
    "Momentum": {"technical": .40, "sentiment": .20, "fundamental": .10, "risk_adjusted": .20, "sector_context": .10},
    "Event Recovery": {"recovery": .35, "valuation": .15, "sentiment": .20, "fundamental": .10, "risk_adjusted": .10, "sector_context": .10},
}


def _num(value: Any) -> float | None:
    try:
        number = float(value)
        return number if math.isfinite(number) else None
    except (TypeError, ValueError):
        return None


def _first(row: Mapping[str, Any], *names: str) -> tuple[float | None, str]:
    for name in names:
        value = _num(row.get(name))
        if value is not None:
            return value, name
    return None, names[0]


def _clamp(value: float) -> float:
    return round(max(0.0, min(100.0, value)), 2)


def _percent_like(value: float | None) -> float | None:
    if value is None:
        return None
    return value * 100.0 if -1.0 <= value <= 1.0 else value


def _linear(value: float | None, low: float, high: float, *, inverse: bool = False) -> float | None:
    if value is None or high == low:
        return None
    score = (value - low) / (high - low) * 100.0
    return _clamp(100.0 - score if inverse else score)


def canonical_sector(value: Any) -> str:
    raw = str(value or "Unknown").strip()
    return SECTOR_ALIASES.get(raw.casefold(), raw if raw in SECTOR_BENCHMARKS else "Unknown")


@dataclass(frozen=True)
class StrategyResult:
    strategy: str
    score: float
    confidence: float
    matched: bool
    sector: str
    contributions: tuple[Mapping[str, Any], ...]
    positives: tuple[str, ...]
    cautions: tuple[str, ...]
    missing_data: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        value = asdict(self)
        for key in ("contributions", "positives", "cautions", "missing_data"):
            value[key] = list(value[key])
        return value


def analyze_candidate(row: Mapping[str, Any], derived: Mapping[str, Any], *, adaptive_meta: Mapping[str, Any] | None = None) -> dict[str, Any]:
    sector = canonical_sector(row.get("sector") or row.get("industry"))
    benchmark = SECTOR_BENCHMARKS[sector]
    pe, pe_field = _first(row, "forward_pe", "trailing_pe", "pe")
    growth, growth_field = _first(row, "earnings_growth", "eps_growth", "revenue_growth", "growth_score")
    dividend, dividend_field = _first(row, "dividend_yield", "dividendYield", "yield_pct", "yield")
    technical, technical_field = _first(row, "technical_score", "trend_score", "momentum_score", "strength")
    insider, insider_field = _first(row, "insider_score")
    sentiment, sentiment_field = _first(row, "news_score", "sentiment_score", "research_score")
    drawdown, drawdown_field = _first(row, "max_drawdown_pct", "max_drawdown", "drawdown")
    change_1m, change_field = _first(row, "return_1m", "change_1m", "monthly_return")
    growth = _percent_like(growth); dividend = _percent_like(dividend)
    drawdown = _percent_like(drawdown); change_1m = _percent_like(change_1m)
    technical = _percent_like(technical)

    valuation = None if pe is None or pe <= 0 else _clamp(100 - abs(pe - benchmark["pe_anchor"]) / max(benchmark["pe_anchor"], 1) * 80)
    growth_score = _linear(growth, -10, benchmark["growth_good"])
    income_score = _linear(dividend, 0, benchmark["yield_good"])
    technical_score = _clamp(technical if technical is not None else float(derived.get("discovery", 50)))
    insider_score = _clamp(insider) if insider is not None else None
    sentiment_score = _clamp(sentiment) if sentiment is not None else None
    fundamental_score = _clamp(float(derived.get("fundamental", 50)))
    risk_adjusted = _clamp(100 - float(derived.get("risk", 50)))
    recovery = None
    if drawdown is not None or change_1m is not None:
        setback = _linear(abs(drawdown or 0), 5, 45)
        turn = _linear(change_1m, -10, 12)
        recovery = _clamp(.55 * (setback if setback is not None else 50) + .45 * (turn if turn is not None else 50))
    sector_inputs = [value for value in (valuation, growth_score, income_score, risk_adjusted) if value is not None]
    sector_context = _clamp(sum(sector_inputs) / len(sector_inputs)) if sector_inputs else 50.0

    components = {
        "fundamental": (fundamental_score, "derived.fundamental", derived.get("fundamental")),
        "risk_adjusted": (risk_adjusted, "derived.risk", derived.get("risk")),
        "valuation": (valuation, pe_field, pe), "growth": (growth_score, growth_field, growth),
        "income": (income_score, dividend_field, dividend), "technical": (technical_score, technical_field, technical),
        "insider": (insider_score, insider_field, insider), "sentiment": (sentiment_score, sentiment_field, sentiment),
        "recovery": (recovery, f"{drawdown_field}+{change_field}", {"drawdown": drawdown, "change_1m": change_1m}),
        "sector_context": (sector_context, f"sector_benchmark.{sector}", dict(benchmark)),
    }
    results: dict[str, dict[str, Any]] = {}
    for strategy, weights in STRATEGY_WEIGHTS.items():
        contributions = []; missing = []; weighted = 0.0; used = 0.0
        for component, weight in weights.items():
            score, field, raw = components[component]
            if score is None:
                missing.append(field); continue
            contribution = float(score) * weight
            contributions.append({"component": component, "field": field, "raw_value": raw, "component_score": score, "weight": weight, "contribution": round(contribution, 2)})
            weighted += contribution; used += weight
        score = _clamp(weighted / used) if used else 50.0
        coverage = used / sum(weights.values())
        confidence = _clamp(float(derived.get("confidence", 50)) * (.55 + .45 * coverage))
        matched = bool(score >= 65 and confidence >= 55 and coverage >= .60)
        positives = tuple(f"{item['component']} bidrar positivt ({item['component_score']:.0f}/100)" for item in contributions if float(item["component_score"]) >= 65)
        cautions = tuple(f"{item['component']} er svakt ({item['component_score']:.0f}/100)" for item in contributions if float(item["component_score"]) < 40)
        results[strategy] = StrategyResult(strategy, score, confidence, matched, sector, tuple(contributions), positives, cautions, tuple(missing)).to_dict()

    matches = sorted((name for name, result in results.items() if result["matched"]), key=lambda name: results[name]["score"], reverse=True)
    scenarios = {
        "positive": {name: _clamp(result["score"] + (6 if name in {"Growth", "Momentum", "Event Recovery"} else 3)) for name, result in results.items()},
        "base": {name: result["score"] for name, result in results.items()},
        "stress": {name: _clamp(result["score"] - (12 if name in {"Growth", "Momentum", "Event Recovery"} else 7) - float(derived.get("risk", 50)) * .05) for name, result in results.items()},
        "note": "Scenarioene viser strategifølsomhet, ikke kursmål eller prognose.",
    }
    return {
        "version": LAYER_VERSION, "sector": sector, "sector_benchmark": dict(benchmark),
        "strategies": results, "matches": matches, "match_count": len(matches),
        "scenario_analysis": scenarios,
        "adaptive_ranking": dict(adaptive_meta or {}),
        "universal_score_created": False,
        "match_thresholds": {"score": 65, "confidence": 55, "coverage": .60},
        "explainability": "Hver strategi viser råfelt, komponentpoeng, vekt og bidrag; manglende felt reduserer dekning og konfidens.",
    }
