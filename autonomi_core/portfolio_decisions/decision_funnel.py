"""Explainable purchase-gate audit for Autonomy.

The module is diagnostic only.  It mirrors the production gates without
changing parameters or placing trades.  RC9 deliberately separates the
analytical investment assessment from execution constraints in Autonomis
primary simulated portfolio.  A full simulated portfolio must therefore be
reported as an execution block, not as proof that the security itself is a
poor analytical candidate.
"""
from __future__ import annotations

from collections import Counter
from typing import Any, Mapping, MutableMapping, Sequence

from app_version import APP_VERSION

VERSION = APP_VERSION
# Calibration challengers are observational.  They never change production.
# The range deliberately brackets the current score distribution so candidate
# recall can be measured before a new production threshold is approved.
SHADOW_THRESHOLDS = (78.0, 76.0, 74.0, 73.0, 72.0, 70.0, 68.0, 65.0)
PORTFOLIO_NAME = "Autonomis primære simulerte portefølje"


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
        position = dict(raw or {})
        ticker = str(ticker).upper()
        trade = dict(trade_by_ticker.get(ticker) or {})
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
        rows.append({
            "ticker": ticker,
            "origin": origin,
            "source_run_id": run_id or "-",
            "opened_at": position.get("opened_at") or trade.get("timestamp") or "-",
            "evidence": "VERIFIED" if trade else "POSITION_ONLY",
        })
    return rows


def _failed_reasons(gates: Mapping[str, bool], labels: Mapping[str, str], counter: Counter[str]) -> list[str]:
    reasons: list[str] = []
    for gate, passed in gates.items():
        if not passed:
            reasons.append(labels[gate])
            counter[gate] += 1
    return reasons


def build_decision_funnel(
    candidates: Sequence[Mapping[str, Any]],
    *,
    parameters: Any,
    portfolio: Mapping[str, Any],
    trades: Sequence[Mapping[str, Any]] = (),
) -> dict[str, Any]:
    """Build an explainable mirror of analytical and execution gates.

    ``analytical_recommendation`` is independent of portfolio capacity and the
    portfolio layer's action. ``trade_execution_status`` then explains whether
    that analytical recommendation can be acted on in Autonomis primary
    simulated portfolio. Existing ``gates`` and ``decision`` fields are kept as
    compatibility mirrors of the complete production gate set.
    """
    from decision_inputs import candidate_entry_score, candidate_price

    production_threshold = _num(getattr(parameters, "minimum_investment_score", 78.0), 78.0)
    min_quality = _num(getattr(parameters, "minimum_data_quality", 55.0), 55.0)
    max_risk = _num(getattr(parameters, "maximum_risk_score", 65.0), 65.0)
    max_positions = int(_num(getattr(parameters, "maximum_open_positions", 12), 12))
    active = str(portfolio.get("status") or "").upper() == "ACTIVE"
    open_positions = dict(portfolio.get("positions") or {})
    allow_additions = bool(getattr(parameters, "allow_additions", False))

    rows: list[dict[str, Any]] = []
    reason_counts: Counter[str] = Counter()
    analytical_counts: Counter[str] = Counter()
    execution_counts: Counter[str] = Counter()

    for candidate in sorted(candidates, key=lambda row: _num(row.get("investment_score")), reverse=True):
        ticker = str(candidate.get("ticker") or "").upper()
        score = candidate_entry_score(candidate)
        quality, quality_source = _quality(candidate)
        risk = _num(candidate.get("risk_score"), 100.0)
        price = candidate_price(candidate, open_positions.get(ticker))
        portfolio_action = str(candidate.get("portfolio_action") or "UNASSESSED").upper()
        outcome = str(candidate.get("autonomy_outcome_code") or "").upper()

        analytical_gates = {
            "mission_eligible": bool(candidate.get("mission_eligible", True)),
            "valid_for_decision": candidate.get("valid_for_decision") is True,
            "evidence_valid_for_decision": candidate.get("evidence_valid_for_decision") is True,
            "technical_timing": not bool(candidate.get("technical_entry_wait")),
            "score": score >= production_threshold,
            "data_quality": quality >= min_quality,
            "risk": risk <= max_risk,
            "price": price > 0,
        }
        analytical_labels = {
            "mission_eligible": "Kandidaten er utenfor det valgte investeringsoppdraget",
            "valid_for_decision": "Markedsdata er ikke beslutningsgyldige",
            "evidence_valid_for_decision": "Evidensgrunnlaget er ikke beslutningsgyldig",
            "technical_timing": str(candidate.get("technical_entry_wait_reason") or "Teknisk timing gir Vent"),
            "score": f"Score {score:.1f} er under {production_threshold:.1f}",
            "data_quality": f"Datakvalitet {quality:.1f} er under {min_quality:.1f}",
            "risk": f"Risiko {risk:.1f} er over {max_risk:.1f}",
            "price": "Mangler gyldig markedspris",
        }
        analytical_reasons = _failed_reasons(analytical_gates, analytical_labels, analytical_counts)
        strict_analytical_buy = all(analytical_gates.values())
        moderate_analytical_buy = outcome == "MODERAT_KJØPSANBEFALING"
        analytical_buy = strict_analytical_buy or moderate_analytical_buy

        execution_gates = {
            "portfolio_active": active,
            "position_capacity": len(open_positions) < max_positions or ticker in open_positions,
            "addition_policy": ticker not in open_positions or allow_additions,
            "portfolio_layer_buy": portfolio_action in {"BUY", "KJØP"},
            "autonomy_outcome_buy": outcome == "KJØPSKANDIDAT",
        }
        execution_labels = {
            "portfolio_active": f"{PORTFOLIO_NAME} er ikke aktiv",
            "position_capacity": f"{PORTFOLIO_NAME} har nådd maks {max_positions} åpne posisjoner",
            "addition_policy": "Finnes allerede i porteføljen; tilleggskjøp er deaktivert",
            "portfolio_layer_buy": f"Porteføljelaget ga {portfolio_action}",
            "autonomy_outcome_buy": f"Autonomiutfallet er {outcome or 'ikke satt'}, ikke Kjøpskandidat",
        }
        trade_reasons = _failed_reasons(execution_gates, execution_labels, execution_counts)
        portfolio_capacity_blocked = not execution_gates["position_capacity"]
        portfolio_constraints_pass = (
            execution_gates["portfolio_active"]
            and execution_gates["position_capacity"]
            and execution_gates["addition_policy"]
        )
        production_gate_pass = analytical_buy and all(execution_gates.values())

        if not analytical_buy:
            analytical_code = "NOT_RECOMMENDED"
            analytical_label = "Ikke analytisk kjøpsanbefalt"
            execution_status = "NOT_ANALYTICALLY_RECOMMENDED"
            execution_label = "Ingen handel - analytiske krav er ikke bestått"
        else:
            analytical_code = "MODERATE_BUY_RECOMMENDED" if moderate_analytical_buy else "BUY_RECOMMENDED"
            analytical_label = "Moderat kjøpsanbefaling" if moderate_analytical_buy else "Analytisk kjøpsanbefaling"
            if production_gate_pass:
                execution_status = "EXECUTABLE"
                execution_label = "Klar i Autonomis simulerte portefølje"
            elif not portfolio_constraints_pass:
                execution_status = "BLOCKED_AUTONOMY_PORTFOLIO"
                execution_label = "Kjøpsanbefaling - handel blokkert av Autonomis portefølje"
            else:
                execution_status = "BLOCKED_PRODUCTION_DECISION_CHAIN"
                execution_label = "Kjøpsanbefaling - ikke godkjent av produksjonskjeden"

        gates = {
            "portfolio_active": execution_gates["portfolio_active"],
            "autonomy_outcome_buy": execution_gates["autonomy_outcome_buy"],
            "portfolio_layer_buy": execution_gates["portfolio_layer_buy"],
            "valid_for_decision": analytical_gates["valid_for_decision"],
            "evidence_valid_for_decision": analytical_gates["evidence_valid_for_decision"],
            # Compatibility field: production final readiness remains unchanged.
            "final_decision_ready": candidate.get("final_decision_ready") is not False,
            "technical_timing": analytical_gates["technical_timing"],
            "score": analytical_gates["score"],
            "data_quality": analytical_gates["data_quality"],
            "risk": analytical_gates["risk"],
            "price": analytical_gates["price"],
            "position_capacity": execution_gates["position_capacity"],
            "addition_policy": execution_gates["addition_policy"],
        }
        compatibility_labels = {
            **execution_labels,
            **analytical_labels,
            "final_decision_ready": "Kandidaten er ikke endelig kjøpsklar i produksjonskjeden",
        }
        compatibility_reasons: list[str] = []
        for gate, passed in gates.items():
            if not passed:
                compatibility_reasons.append(compatibility_labels[gate])
                reason_counts[gate] += 1

        rows.append({
            "ticker": ticker,
            "market": candidate.get("market"),
            "score": round(score, 2),
            "production_threshold": production_threshold,
            "score_gap": round(score - production_threshold, 2),
            "data_quality": round(quality, 2),
            "data_quality_source": quality_source,
            "risk": round(risk, 2),
            "price": price,
            "portfolio_name": PORTFOLIO_NAME,
            "portfolio_action": portfolio_action,
            "autonomy_outcome_code": outcome,
            "analytical_gates": analytical_gates,
            "execution_gates": execution_gates,
            "analytical_recommendation": analytical_code,
            "analytical_recommendation_label": analytical_label,
            "analytical_reasons": analytical_reasons,
            "trade_execution_status": execution_status,
            "trade_execution_label": execution_label,
            "trade_reasons": trade_reasons,
            "portfolio_capacity_blocked": portfolio_capacity_blocked,
            "would_be_buy_without_autonomy_portfolio_constraints": bool(
                analytical_buy and not portfolio_constraints_pass
            ),
            "gates": gates,
            "eligible_for_theoretical_buy": production_gate_pass,
            "decision": "BUY_ELIGIBLE" if production_gate_pass else "REJECTED",
            "reasons": compatibility_reasons,
        })

    shadows = []
    for threshold in dict.fromkeys((production_threshold, *SHADOW_THRESHOLDS)):
        score_qualified = [row["ticker"] for row in rows if row["score"] >= threshold]
        analytical_eligible = [
            row["ticker"]
            for row in rows
            if all(value for key, value in row["analytical_gates"].items() if key != "score")
            and row["score"] >= threshold
        ]
        production_eligible = [
            row["ticker"]
            for row in rows
            if all(value for key, value in row["gates"].items() if key != "score")
            and row["score"] >= threshold
        ]
        shadows.append({
            "threshold": threshold,
            "role": "PRODUCTION" if threshold == production_threshold else "CHALLENGER",
            "score_qualified_count": len(score_qualified),
            "score_qualified_tickers": score_qualified,
            "analytical_eligible_count": len(analytical_eligible),
            "analytical_eligible_tickers": analytical_eligible,
            "eligible_count": len(production_eligible),
            "eligible_tickers": production_eligible,
            "changes_production": False,
        })

    near = [row for row in rows if not row["eligible_for_theoretical_buy"] and row["score"] >= production_threshold - 6]
    analytical_buy_count = sum(row["analytical_recommendation"] in {"BUY_RECOMMENDED", "MODERATE_BUY_RECOMMENDED"} for row in rows)
    trade_executable_count = sum(row["trade_execution_status"] == "EXECUTABLE" for row in rows)
    portfolio_blocked_count = sum(row["trade_execution_status"] == "BLOCKED_AUTONOMY_PORTFOLIO" for row in rows)
    capacity_blocked_count = sum(
        row["analytical_recommendation"] in {"BUY_RECOMMENDED", "MODERATE_BUY_RECOMMENDED"} and row["portfolio_capacity_blocked"]
        for row in rows
    )
    return {
        "version": VERSION,
        "mode": "DIAGNOSTIC_ONLY",
        "portfolio_name": PORTFOLIO_NAME,
        "production_threshold": production_threshold,
        "production_threshold_changed": False,
        "approval_required_for_change": True,
        "evaluated": len(rows),
        "eligible": sum(row["eligible_for_theoretical_buy"] for row in rows),
        "rejected": sum(not row["eligible_for_theoretical_buy"] for row in rows),
        "analytical_buy_recommendations": analytical_buy_count,
        "trade_executable": trade_executable_count,
        "portfolio_blocked_buy_recommendations": portfolio_blocked_count,
        "capacity_blocked_buy_recommendations": capacity_blocked_count,
        "analytical_rejection_counts": dict(analytical_counts),
        "execution_block_counts": dict(execution_counts),
        "rejection_counts": dict(reason_counts),
        "candidates": rows,
        "near_threshold": near[:10],
        "shadow_thresholds": shadows,
        "position_provenance": _position_provenance(portfolio, trades),
        "warning": "Diagnostikken endrer aldri produksjonsterskel, rangering eller handelsregler uten eksplisitt godkjenning.",
    }


def apply_funnel_annotations(
    candidates: Sequence[MutableMapping[str, Any]], funnel: Mapping[str, Any]
) -> Sequence[MutableMapping[str, Any]]:
    """Copy RC9 diagnostic labels into report candidates without changing score."""
    by_ticker = {
        str(row.get("ticker") or "").upper(): row
        for row in (funnel.get("candidates") or [])
        if isinstance(row, Mapping)
    }
    for candidate in candidates:
        row = by_ticker.get(str(candidate.get("ticker") or "").upper())
        if not row:
            continue
        for key in (
            "portfolio_name",
            "analytical_recommendation",
            "analytical_recommendation_label",
            "analytical_reasons",
            "trade_execution_status",
            "trade_execution_label",
            "trade_reasons",
            "portfolio_capacity_blocked",
            "would_be_buy_without_autonomy_portfolio_constraints",
            "analytical_gates",
            "execution_gates",
        ):
            candidate[key] = row.get(key)
    return candidates
