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

VERSION = "v18.6.92"
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


def derive_scores(row: Mapping[str, Any]) -> dict[str, Any]:
    """Derive component scores from real fields and report provenance/completeness."""
    present: list[str] = []
    reasons: list[str] = []

    direct_discovery = first(row, ("ai_score", "smart_score", "score", "signal_score"))
    momentum_raw = first(row, ("momentum_score", "strength", "relative_strength", "rsi_score"))
    change_1m = first(row, ("return_1m", "change_1m", "monthly_return", "performance_1m"))
    change_3m = first(row, ("return_3m", "change_3m", "quarter_return", "performance_3m"))
    trend = first(row, ("trend_score", "technical_score"))
    momentum_parts = []
    if direct_discovery is not None:
        present.append("ai_score")
        momentum_parts.append(normalized(direct_discovery))
    if momentum_raw is not None:
        present.append("momentum")
        momentum_parts.append(normalized(momentum_raw))
    if change_1m is not None:
        present.append("return_1m")
        momentum_parts.append(bounded_linear(change_1m, -15, 15))
    if change_3m is not None:
        present.append("return_3m")
        momentum_parts.append(bounded_linear(change_3m, -25, 30))
    if trend is not None:
        present.append("trend")
        momentum_parts.append(normalized(trend))
    discovery = sum(momentum_parts) / len(momentum_parts) if momentum_parts else 50.0

    fundamental_parts = []
    direct_fund = first(row, ("fundamental_score", "quality_score"))
    if direct_fund is not None:
        present.append("fundamental_score")
        fundamental_parts.append(normalized(direct_fund))
    roe = first(row, ("roe", "return_on_equity"))
    if roe is not None:
        present.append("roe")
        fundamental_parts.append(bounded_linear(roe, 0, 25))
    growth = first(row, ("earnings_growth", "eps_growth", "revenue_growth", "growth_score"))
    if growth is not None:
        present.append("growth")
        fundamental_parts.append(normalized(growth) if abs(growth) <= 10 else bounded_linear(growth, -15, 30))
    debt = first(row, ("debt_to_equity", "debt_equity", "net_debt_ebitda"))
    if debt is not None:
        present.append("debt")
        fundamental_parts.append(bounded_linear(debt, 0, 250, inverse=True))
    pe = first(row, ("pe", "trailing_pe", "forward_pe"))
    if pe is not None and pe > 0:
        present.append("pe")
        fundamental_parts.append(100 - min(100, abs(pe - 18) * 3.5))
    fundamental = sum(fundamental_parts) / len(fundamental_parts) if fundamental_parts else 50.0

    research_parts = []
    direct_research = first(row, ("research_score", "sentiment_score", "news_score", "sentiment"))
    if direct_research is not None:
        present.append("research")
        research_parts.append(normalized(direct_research))
    analyst = first(row, ("analyst_score", "recommendation_score", "target_upside"))
    if analyst is not None:
        present.append("analyst")
        research_parts.append(normalized(analyst) if abs(analyst) <= 10 else bounded_linear(analyst, -20, 35))
    research = sum(research_parts) / len(research_parts) if research_parts else 50.0

    validation_parts = []
    direct_validation = first(row, ("backtest_score", "validation_score", "strategy_score"))
    if direct_validation is not None:
        present.append("validation")
        validation_parts.append(normalized(direct_validation))
    sharpe = first(row, ("sharpe", "sharpe_ratio"))
    if sharpe is not None:
        present.append("sharpe")
        validation_parts.append(bounded_linear(sharpe, -0.5, 2.0))
    win_rate = first(row, ("win_rate", "win_rate_pct"))
    if win_rate is not None:
        present.append("win_rate")
        validation_parts.append(normalized(win_rate))
    validation = sum(validation_parts) / len(validation_parts) if validation_parts else 50.0

    risk_parts = []
    direct_risk = first(row, ("risk_score",))
    if direct_risk is not None:
        present.append("risk_score")
        risk_parts.append(normalized(direct_risk))
    volatility = first(row, ("volatility", "volatility_pct", "annual_volatility"))
    if volatility is not None:
        present.append("volatility")
        risk_parts.append(bounded_linear(volatility, 8, 55))
    beta = first(row, ("beta",))
    if beta is not None:
        present.append("beta")
        risk_parts.append(bounded_linear(abs(beta - 0.7), 0, 1.5))
    drawdown = first(row, ("max_drawdown", "max_drawdown_pct", "drawdown"))
    if drawdown is not None:
        present.append("drawdown")
        risk_parts.append(bounded_linear(abs(drawdown), 5, 45))
    risk = sum(risk_parts) / len(risk_parts) if risk_parts else 50.0

    liquidity_parts = []
    direct_liq = first(row, ("liquidity_score", "volume_score"))
    if direct_liq is not None:
        present.append("liquidity_score")
        liquidity_parts.append(normalized(direct_liq))
    avg_volume = first(row, ("average_volume", "avg_volume", "volume"))
    if avg_volume is not None and avg_volume > 0:
        present.append("volume")
        liquidity_parts.append(bounded_linear(math.log10(max(avg_volume, 1)), 3, 7))
    liquidity = sum(liquidity_parts) / len(liquidity_parts) if liquidity_parts else 50.0

    direct_quality = first(row, ("data_quality", "quality", "data_quality_score"))
    expected_groups = 6
    covered_groups = sum(bool(x) for x in (momentum_parts, fundamental_parts, research_parts, validation_parts, risk_parts, liquidity_parts))
    completeness = covered_groups / expected_groups
    data_quality = normalized(direct_quality, 35 + completeness * 65) if direct_quality is not None else 35 + completeness * 65
    confidence = clamp(25 + completeness * 65 + min(len(set(present)), 10) * 1.0)

    if discovery >= 65:
        reasons.append("Teknisk/momentum-basert signal er positivt.")
    if fundamental >= 65:
        reasons.append("Fundamentale nøkkeltall trekker opp.")
    if research >= 65:
        reasons.append("Research/sentiment trekker opp.")
    if risk >= 65:
        reasons.append("Volatilitet eller annen målt risiko er høy.")
    if confidence < 55:
        reasons.append("Konfidensen er begrenset fordi få individuelle datapunkter var tilgjengelige.")

    return {
        "discovery": clamp(discovery), "fundamental": clamp(fundamental), "research": clamp(research),
        "validation": clamp(validation), "risk": clamp(risk), "liquidity": clamp(liquidity),
        "data_quality": clamp(data_quality), "confidence": clamp(confidence),
        "data_fields_used": sorted(set(present)), "explanation_reasons": reasons,
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
