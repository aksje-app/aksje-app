"""Advanced Investment Intelligence v18.6.92.

Deterministic, explainable scoring helpers for Investment Pipeline. The module
uses only fields actually present in candidate data, records data completeness,
adds candidate trend metadata and creates a risk-aware theoretical portfolio
proposal. Missing inputs stay neutral and reduce confidence; they are never
invented.
"""
from __future__ import annotations

import json
import math
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Sequence

from storage_architecture import runtime_data_path

VERSION = "v18.6.92c"
HISTORY_PATH = runtime_data_path("market_intelligence") / "candidate_history.json"
TRADES_PATH = runtime_data_path("autonomous_portfolio") / "trades.json"
WEIGHTS_PATH = runtime_data_path("investment_pipeline") / "adaptive_weights.json"


def f(value: Any, default: float | None = None) -> float | None:
    try:
        number = float(value)
        return number if math.isfinite(number) else default
    except Exception:
        return default


def clamp(value: float, lo: float = 0.0, hi: float = 100.0) -> float:
    return max(lo, min(hi, float(value)))


def first(row: Mapping[str, Any], names: Sequence[str]) -> float | None:
    for name in names:
        if name in row and row.get(name) not in (None, ""):
            value = f(row.get(name))
            if value is not None:
                return value
    return None


def normalized(value: float | None, fallback: float = 50.0) -> float:
    if value is None:
        return fallback
    if -1.0 <= value <= 1.0:
        value *= 100.0
    elif 0.0 <= value <= 10.0:
        value *= 10.0
    return clamp(value)


def bounded_linear(value: float | None, bad: float, good: float, fallback: float = 50.0, inverse: bool = False) -> float:
    if value is None or good == bad:
        return fallback
    score = (value - bad) / (good - bad) * 100.0
    if inverse:
        score = 100.0 - score
    return clamp(score)


def _component(name: str, entries: list[dict[str, Any]], neutral: float = 50.0) -> tuple[float, dict[str, Any]]:
    valid = [e for e in entries if e.get("value") is not None]
    if not valid:
        return neutral, {"component": name, "score": neutral, "inputs": [], "coverage": 0.0, "status": "MISSING"}
    total_weight = sum(float(e.get("weight", 1.0)) for e in valid) or 1.0
    score = sum(float(e["score"]) * float(e.get("weight", 1.0)) for e in valid) / total_weight
    return clamp(score), {
        "component": name,
        "score": round(clamp(score), 2),
        "inputs": valid,
        "coverage": round(min(1.0, len(valid) / max(1, len(entries))), 3),
        "status": "OK",
    }


def derive_scores(row: Mapping[str, Any]) -> dict[str, Any]:
    """Derive transparent component scores and calibrated confidence from actual data."""
    present: list[str] = []
    reasons: list[str] = []
    traces: dict[str, Any] = {}

    def add(entries: list[dict[str, Any]], field: str, raw: float | None, score: float | None, weight: float = 1.0, note: str = "") -> None:
        entries.append({"field": field, "value": raw, "score": None if score is None else round(clamp(score), 2), "weight": weight, "note": note})
        if raw is not None:
            present.append(field)

    discovery_entries: list[dict[str, Any]] = []
    direct_discovery = first(row, ("ai_score", "smart_score", "score", "signal_score"))
    momentum_raw = first(row, ("momentum_score", "strength", "relative_strength", "rsi_score"))
    change_1m = first(row, ("return_1m", "change_1m", "monthly_return", "performance_1m"))
    change_3m = first(row, ("return_3m", "change_3m", "quarter_return", "performance_3m"))
    trend = first(row, ("trend_score", "technical_score"))
    add(discovery_entries, "ai_score", direct_discovery, normalized(direct_discovery) if direct_discovery is not None else None, 0.8)
    add(discovery_entries, "momentum", momentum_raw, normalized(momentum_raw) if momentum_raw is not None else None, 1.0)
    add(discovery_entries, "return_1m", change_1m, bounded_linear(change_1m, -15, 15) if change_1m is not None else None, 1.0)
    add(discovery_entries, "return_3m", change_3m, bounded_linear(change_3m, -25, 30) if change_3m is not None else None, 1.1)
    add(discovery_entries, "trend", trend, normalized(trend) if trend is not None else None, 1.1)
    discovery, traces["discovery"] = _component("AI Discovery", discovery_entries)

    fundamental_entries: list[dict[str, Any]] = []
    direct_fund = first(row, ("fundamental_score", "quality_score"))
    roe = first(row, ("roe", "return_on_equity"))
    growth = first(row, ("earnings_growth", "eps_growth", "revenue_growth", "growth_score"))
    debt = first(row, ("debt_to_equity", "debt_equity", "net_debt_ebitda"))
    pe = first(row, ("pe", "trailing_pe", "forward_pe"))
    add(fundamental_entries, "fundamental_score", direct_fund, normalized(direct_fund) if direct_fund is not None else None, 0.7)
    add(fundamental_entries, "roe", roe, bounded_linear(roe, 0, 25) if roe is not None else None, 1.2)
    growth_score = None if growth is None else (normalized(growth) if abs(growth) <= 1 else bounded_linear(growth, -15, 30))
    add(fundamental_entries, "growth", growth, growth_score, 1.1)
    add(fundamental_entries, "debt", debt, bounded_linear(debt, 0, 250, inverse=True) if debt is not None else None, 1.0)
    pe_score = None if pe is None or pe <= 0 else 100 - min(100, abs(pe - 18) * 3.5)
    add(fundamental_entries, "pe", pe, pe_score, 0.9)
    fundamental, traces["fundamental"] = _component("Fundamentaler", fundamental_entries)

    research_entries: list[dict[str, Any]] = []
    direct_research = first(row, ("research_score", "sentiment_score", "news_score", "sentiment"))
    recommendation = first(row, ("recommendation_score", "analyst_score"))
    target_upside = first(row, ("target_upside",))
    add(research_entries, "research_score", direct_research, normalized(direct_research) if direct_research is not None else None, 1.0)
    add(research_entries, "recommendation_score", recommendation, normalized(recommendation) if recommendation is not None else None, 1.0)
    add(research_entries, "target_upside", target_upside, bounded_linear(target_upside, -25, 45) if target_upside is not None else None, 0.8)
    research, traces["research"] = _component("Research", research_entries)
    research_count = len([e for e in research_entries if e.get("value") is not None])
    if research_count == 1:
        research = 50.0 + (research - 50.0) * 0.65
        traces["research"]["score"] = round(research, 2)
        traces["research"]["note"] = "Én research-kilde; utslaget er dempet."

    validation_entries: list[dict[str, Any]] = []
    direct_validation = first(row, ("backtest_score", "validation_score", "strategy_score"))
    sharpe = first(row, ("sharpe", "sharpe_ratio"))
    win_rate = first(row, ("win_rate", "win_rate_pct"))
    add(validation_entries, "validation_score", direct_validation, normalized(direct_validation) if direct_validation is not None else None, 0.8)
    add(validation_entries, "sharpe", sharpe, bounded_linear(sharpe, -0.5, 2.0) if sharpe is not None else None, 1.2)
    add(validation_entries, "win_rate", win_rate, normalized(win_rate) if win_rate is not None else None, 1.0)
    validation, traces["validation"] = _component("Historisk validering", validation_entries)

    risk_entries: list[dict[str, Any]] = []
    direct_risk = first(row, ("risk_score",))
    volatility = first(row, ("volatility", "volatility_pct", "annual_volatility"))
    beta = first(row, ("beta",))
    drawdown = first(row, ("max_drawdown", "max_drawdown_pct", "drawdown"))
    add(risk_entries, "risk_score", direct_risk, normalized(direct_risk) if direct_risk is not None else None, 0.7)
    add(risk_entries, "volatility", volatility, bounded_linear(volatility, 8, 55) if volatility is not None else None, 1.2)
    add(risk_entries, "beta", beta, bounded_linear(abs(beta - 0.7), 0, 1.5) if beta is not None else None, 0.9)
    add(risk_entries, "drawdown", drawdown, bounded_linear(abs(drawdown), 5, 45) if drawdown is not None else None, 1.2)
    risk, traces["risk"] = _component("Risiko", risk_entries)

    liquidity_entries: list[dict[str, Any]] = []
    direct_liq = first(row, ("liquidity_score", "volume_score"))
    avg_volume = first(row, ("average_volume", "avg_volume", "volume"))
    add(liquidity_entries, "liquidity_score", direct_liq, normalized(direct_liq) if direct_liq is not None else None, 0.8)
    liq_score = bounded_linear(math.log10(max(avg_volume, 1)), 3, 7) if avg_volume is not None and avg_volume > 0 else None
    add(liquidity_entries, "average_volume", avg_volume, liq_score, 1.2)
    liquidity, traces["liquidity"] = _component("Likviditet", liquidity_entries)

    groups = [traces[k] for k in ("discovery", "fundamental", "research", "validation", "risk", "liquidity")]
    group_coverage = sum(1 for g in groups if g["status"] == "OK") / len(groups)
    expected_fields = 18.0
    field_depth = min(1.0, len(set(present)) / expected_fields)
    source_status = str(row.get("data_fetch_status") or "").upper()
    source_factor = 1.0 if source_status == "OK" else 0.92 if source_status == "CACHE" else 0.65 if source_status in {"NO_DATA", "ERROR"} else 0.85
    direct_quality = first(row, ("data_quality", "quality", "data_quality_score"))
    calculated_quality = (35.0 + 35.0 * group_coverage + 30.0 * field_depth) * source_factor
    data_quality = normalized(direct_quality, calculated_quality) if direct_quality is not None else calculated_quality
    confidence = clamp((15.0 + 45.0 * group_coverage + 35.0 * field_depth) * source_factor, 5.0, 96.0)
    if research_count == 0:
        confidence = max(5.0, confidence - 6.0)
    if source_status in {"ERROR", "NO_DATA"}:
        confidence = min(confidence, 40.0)

    traces["confidence"] = {
        "component": "Konfidens",
        "score": round(confidence, 2),
        "group_coverage": round(group_coverage, 3),
        "field_depth": round(field_depth, 3),
        "source_status": source_status or "UNKNOWN",
        "source_factor": source_factor,
        "fields_present": len(set(present)),
        "expected_fields": int(expected_fields),
    }

    if discovery >= 65:
        reasons.append("Teknisk/momentum-basert signal er positivt.")
    if fundamental >= 65:
        reasons.append("Fundamentale nøkkeltall trekker opp.")
    if research >= 65:
        reasons.append("Research/sentiment trekker opp.")
    if risk >= 65:
        reasons.append("Volatilitet eller annen målt risiko er høy.")
    if confidence < 60:
        reasons.append("Konfidensen er redusert av manglende datadekning eller svak kildekvalitet.")

    return {
        "discovery": clamp(discovery), "fundamental": clamp(fundamental), "research": clamp(research),
        "validation": clamp(validation), "risk": clamp(risk), "liquidity": clamp(liquidity),
        "data_quality": clamp(data_quality), "confidence": clamp(confidence),
        "data_fields_used": sorted(set(present)), "explanation_reasons": reasons,
        "component_trace": traces,
    }


def calculate_portfolio_fit(row: Mapping[str, Any], universe: Sequence[Mapping[str, Any]]) -> tuple[float, dict[str, Any]]:
    """Estimate diversification fit from sector/market concentration and candidate risk/liquidity."""
    total = max(1, len(universe))
    sector = str(row.get("sector") or row.get("industry") or "Unknown")
    market = str(row.get("market") or row.get("country") or row.get("exchange") or "Unknown")
    sector_count = sum(1 for x in universe if str(x.get("sector") or x.get("industry") or "Unknown") == sector)
    market_count = sum(1 for x in universe if str(x.get("market") or x.get("country") or x.get("exchange") or "Unknown") == market)
    sector_share = sector_count / total
    market_share = market_count / total
    derived = derive_scores(row)
    diversification = clamp(100.0 - sector_share * 65.0 - market_share * 25.0)
    fit = clamp(0.55 * diversification + 0.25 * derived["liquidity"] + 0.20 * (100.0 - derived["risk"]))
    return fit, {
        "component": "Porteføljetilpasning",
        "score": round(fit, 2),
        "sector": sector,
        "market": market,
        "sector_share": round(sector_share, 3),
        "market_share": round(market_share, 3),
        "diversification_score": round(diversification, 2),
        "liquidity_score": round(derived["liquidity"], 2),
        "risk_adjusted_score": round(100.0 - derived["risk"], 2),
    }

def load_candidate_trend(ticker: str, current_score: float) -> dict[str, Any]:
    try:
        data = json.loads(HISTORY_PATH.read_text(encoding="utf-8")) if HISTORY_PATH.exists() else {}
    except Exception:
        data = {}
    observations = list((data.get(ticker) or {}).get("observations") or [])[-20:]
    prior = [f(x.get("score")) for x in observations if f(x.get("score")) is not None]
    if not prior:
        return {"trend": "NY", "score_delta": 0.0, "observations": 0, "average_score": round(current_score, 2)}
    previous = prior[-1]
    delta = current_score - previous
    if delta >= 2:
        trend = "STIGENDE"
    elif delta <= -2:
        trend = "FALLENDE"
    else:
        trend = "STABIL"
    return {"trend": trend, "score_delta": round(delta, 2), "observations": len(prior), "average_score": round(sum(prior) / len(prior), 2)}


def adaptive_weights(base_weights: Mapping[str, float]) -> tuple[dict[str, float], dict[str, Any]]:
    """Conservative learning from closed theoretical trades with stored entry components."""
    weights = {k: max(0.0, float(v)) for k, v in base_weights.items()}
    try:
        trades = json.loads(TRADES_PATH.read_text(encoding="utf-8")) if TRADES_PATH.exists() else []
    except Exception:
        trades = []
    sells = [x for x in trades if x.get("action") == "SELL" and isinstance(x.get("entry_components"), Mapping)]
    if len(sells) < 12:
        total = sum(weights.values()) or 1.0
        return {k: v / total for k, v in weights.items()}, {"active": False, "closed_trades": len(sells), "reason": "Minst 12 lukkede handler kreves"}
    signals: dict[str, list[float]] = {k: [] for k in weights}
    for trade in sells[-100:]:
        outcome = 1.0 if float(trade.get("pnl", 0)) > 0 else -1.0
        for key, value in trade.get("entry_components", {}).items():
            if key in signals:
                signals[key].append(outcome * (float(value) - 50.0) / 50.0)
    learned = dict(weights)
    for key, values in signals.items():
        if values:
            adjustment = max(-0.10, min(0.10, sum(values) / len(values) * 0.08))
            learned[key] *= 1.0 + adjustment
    total = sum(learned.values()) or 1.0
    learned = {k: v / total for k, v in learned.items()}
    return learned, {"active": True, "closed_trades": len(sells), "max_relative_adjustment": 0.10}


def build_portfolio_proposal(candidates: Sequence[Mapping[str, Any]], cash_reserve_pct: float = 15.0, max_position_pct: float = 6.0, max_sector_pct: float = 25.0) -> dict[str, Any]:
    eligible = [dict(x) for x in candidates if float(x.get("investment_score", 0)) >= 60 and float(x.get("confidence_score", 0)) >= 45 and float(x.get("risk_score", 100)) <= 75]
    eligible.sort(key=lambda x: (float(x.get("investment_score", 0)) * float(x.get("confidence_score", 0)) / 100.0), reverse=True)
    budget = max(0.0, 100.0 - cash_reserve_pct)
    allocations: list[dict[str, Any]] = []
    sector_used: dict[str, float] = {}
    for row in eligible:
        if budget <= 0.01:
            break
        sector = str(row.get("sector") or "Unknown")
        quality = float(row.get("investment_score", 0)) * float(row.get("confidence_score", 0)) / 100.0
        risk_multiplier = max(0.25, 1.0 - float(row.get("risk_score", 50)) / 120.0)
        requested = min(max_position_pct, max(0.5, quality / 18.0 * risk_multiplier))
        sector_room = max(0.0, max_sector_pct - sector_used.get(sector, 0.0))
        weight = min(requested, sector_room, budget)
        if weight < 0.5:
            continue
        allocations.append({"ticker": row.get("ticker"), "market": row.get("market"), "sector": sector, "weight_pct": round(weight, 2), "score": row.get("investment_score"), "confidence": row.get("confidence_score"), "risk": row.get("risk_score")})
        sector_used[sector] = sector_used.get(sector, 0.0) + weight
        budget -= weight
    invested = round(sum(x["weight_pct"] for x in allocations), 2)
    return {"created_at": datetime.now(timezone.utc).isoformat(timespec="seconds"), "allocations": allocations, "invested_pct": invested, "cash_pct": round(100.0 - invested, 2), "constraints": {"cash_reserve_pct": cash_reserve_pct, "max_position_pct": max_position_pct, "max_sector_pct": max_sector_pct}}
