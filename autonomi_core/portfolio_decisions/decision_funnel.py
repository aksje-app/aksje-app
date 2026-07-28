"""Canonical purchase-gate evidence for Autonomy v19.14.1.

The module is diagnostic only.  It mirrors the production Autonomous Learning
Portfolio gates and evaluates lower score thresholds as non-authoritative
Shadow challengers.  It never changes parameters or places trades.
"""
from __future__ import annotations

from collections import Counter
from typing import Any, Mapping, Sequence


from app_version import APP_VERSION

VERSION = APP_VERSION
SHADOW_THRESHOLDS = (78.0, 76.0, 74.0, 72.0)


def _num(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return float(default)


def _quality(candidate: Mapping[str, Any]) -> tuple[float, str]:
    """Return exactly the value consumed by the legacy execution gate."""
    if candidate.get("data_quality") is None:
        return 0.0, "MISSING_EXECUTION_FIELD"
    return _num(candidate.get("data_quality")), "CANDIDATE_DATA_QUALITY"


def _position_provenance(portfolio: Mapping[str, Any], trades: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    trade_by_ticker: dict[str, Mapping[str, Any]] = {}
    for trade in trades:
        ticker = str(trade.get("ticker") or "").upper()
        if ticker and str(trade.get("action") or "").upper() in {"BUY", "RECOVERED"} and ticker not in trade_by_ticker:
            trade_by_ticker[ticker] = trade
    rows = []
    for ticker, raw in dict(portfolio.get("positions") or {}).items():
        position = dict(raw or {}); ticker = str(ticker).upper(); trade = dict(trade_by_ticker.get(ticker) or {})
        run_id = str(position.get("source_run_id") or trade.get("run_id") or "")
        recovered = bool(trade.get("recovered")) or run_id.startswith("RECOVERED")
        if recovered:
            origin = "RECOVERED"
        elif trade and str(trade.get("mode") or "").upper() == "THEORETICAL_ONLY":
            origin = "AUTONOMY_THEORETICAL_BUY"
        elif run_id:
            origin = "IMPORTED_OR_LEGACY"
        else:
            origin = "UNKNOWN"
        rows.append({"ticker": ticker, "origin": origin, "source_run_id": run_id or "-",
                     "opened_at": position.get("opened_at") or trade.get("timestamp") or "-",
                     "evidence": "VERIFIED" if trade else "POSITION_ONLY"})
    return rows


def build_decision_funnel(candidates: Sequence[Mapping[str, Any]], *, parameters: Any,
                          portfolio: Mapping[str, Any], trades: Sequence[Mapping[str, Any]] = ()) -> dict[str, Any]:
    """Build an explainable mirror of every pre-buy gate and Shadow outcome."""
    from autonomous_portfolio import candidate_price
    production_threshold = _num(getattr(parameters, "minimum_investment_score", 78.0), 78.0)
    min_quality = _num(getattr(parameters, "minimum_data_quality", 55.0), 55.0)
    max_risk = _num(getattr(parameters, "maximum_risk_score", 65.0), 65.0)
    max_positions = int(_num(getattr(parameters, "maximum_open_positions", 12), 12))
    active = str(portfolio.get("status") or "").upper() == "ACTIVE"
    open_positions = dict(portfolio.get("positions") or {})
    rows: list[dict[str, Any]] = []
    reason_counts: Counter[str] = Counter()
    for candidate in sorted(candidates, key=lambda row: _num(row.get("investment_score")), reverse=True):
        ticker = str(candidate.get("ticker") or "").upper()
        score = _num(candidate.get("investment_score")); quality, quality_source = _quality(candidate)
        risk = _num(candidate.get("risk_score"), 100.0)
        price = candidate_price(candidate, open_positions.get(ticker))
        portfolio_action = str(candidate.get("portfolio_action") or "UNASSESSED").upper()
        outcome = str(candidate.get("autonomy_outcome_code") or "").upper()
        allow_additions = bool(getattr(parameters, "allow_additions", False))
        gates = {
            "portfolio_active": active,
            "autonomy_outcome_buy": outcome == "KJØPSKANDIDAT",
            "portfolio_layer_buy": portfolio_action in {"BUY", "KJØP"},
            "valid_for_decision": candidate.get("valid_for_decision") is True,
            "evidence_valid_for_decision": candidate.get("evidence_valid_for_decision") is True,
            "final_decision_ready": candidate.get("final_decision_ready") is not False,
            "technical_timing": not bool(candidate.get("technical_entry_wait")),
            "score": score >= production_threshold,
            "data_quality": quality >= min_quality,
            "risk": risk <= max_risk,
            "price": price > 0,
            "position_capacity": len(open_positions) < max_positions or ticker in open_positions,
            "addition_policy": ticker not in open_positions or allow_additions,
        }
        reasons = []
        labels = {
            "portfolio_active": "Porteføljen er ikke aktiv",
            "autonomy_outcome_buy": f"Autonomiutfallet er {outcome or 'ikke satt'}, ikke Kjøpskandidat",
            "portfolio_layer_buy": f"Porteføljelaget ga {portfolio_action}",
            "valid_for_decision": "Markedsdata er ikke beslutningsgyldige",
            "evidence_valid_for_decision": "Evidensgrunnlaget er ikke beslutningsgyldig",
            "final_decision_ready": "Kandidaten er ikke endelig kjøpsklar",
            "technical_timing": str(candidate.get("technical_entry_wait_reason") or "Teknisk timing gir Vent"),
            "score": f"Score {score:.1f} er under {production_threshold:.1f}",
            "data_quality": f"Datakvalitet {quality:.1f} er under {min_quality:.1f}",
            "risk": f"Risiko {risk:.1f} er over {max_risk:.1f}", "price": "Mangler gyldig markedspris",
            "position_capacity": f"Maks {max_positions} åpne posisjoner er nådd",
            "addition_policy": "Finnes allerede i porteføljen; tilleggskjøp er deaktivert",
        }
        for gate, passed in gates.items():
            if not passed:
                reasons.append(labels[gate]); reason_counts[gate] += 1
        eligible = all(gates.values())
        rows.append({"ticker": ticker, "market": candidate.get("market"), "score": round(score, 2),
                     "production_threshold": production_threshold, "score_gap": round(score - production_threshold, 2),
                     "data_quality": round(quality, 2), "data_quality_source": quality_source,
                     "risk": round(risk, 2), "price": price, "portfolio_action": portfolio_action,
                     "gates": gates, "eligible_for_theoretical_buy": eligible,
                     "decision": "BUY_ELIGIBLE" if eligible else "REJECTED", "reasons": reasons})
    shadows = []
    for threshold in dict.fromkeys((production_threshold, *SHADOW_THRESHOLDS)):
        score_qualified = [row["ticker"] for row in rows if row["score"] >= threshold]
        eligible = [row["ticker"] for row in rows if all(value for key, value in row["gates"].items() if key != "score") and row["score"] >= threshold]
        shadows.append({"threshold": threshold, "role": "PRODUCTION" if threshold == production_threshold else "CHALLENGER",
                        "score_qualified_count": len(score_qualified), "score_qualified_tickers": score_qualified,
                        "eligible_count": len(eligible), "eligible_tickers": eligible, "changes_production": False})
    near = [row for row in rows if not row["eligible_for_theoretical_buy"] and row["score"] >= production_threshold - 6]
    return {"version": VERSION, "mode": "DIAGNOSTIC_ONLY", "production_threshold": production_threshold,
            "production_threshold_changed": False, "approval_required_for_change": True,
            "evaluated": len(rows), "eligible": sum(row["eligible_for_theoretical_buy"] for row in rows),
            "rejected": sum(not row["eligible_for_theoretical_buy"] for row in rows),
            "rejection_counts": dict(reason_counts), "candidates": rows, "near_threshold": near[:10],
            "shadow_thresholds": shadows, "position_provenance": _position_provenance(portfolio, trades),
            "warning": "Shadow-resultater endrer aldri produksjonsterskelen uten eksplisitt godkjenning."}
