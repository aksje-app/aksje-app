"""Read-only autonomy evaluator for parallel strategy comparison.

This mirrors the visible production gates but never replaces or invokes the
mutating autonomous portfolio engine. The actual Autonomi cycle remains the
execution authority until the shared portfolio engine roadmap phase.
"""
from __future__ import annotations

from typing import Any, Mapping

from domain.market_snapshot import CandidateSnapshot
from domain.strategy_contract import StrategyDecision, StrategyEvaluationContext, build_decision_id


def _float(row: Mapping[str, Any], *keys: str, default: float = 0.0) -> float:
    for key in keys:
        try:
            value = row.get(key)
            if value is not None:
                return float(value)
        except Exception:
            pass
    return float(default)


def _parameters(context: StrategyEvaluationContext) -> Any:
    supplied = (context.metadata or {}).get("autonomy_parameters")
    if supplied is not None:
        return supplied
    from autonomous_portfolio import load_parameters
    return load_parameters().normalized()


class AutonomyStrategy:
    def __init__(self, version: Mapping[str, Any]):
        self.version = dict(version or {})

    def evaluate(self, candidate: CandidateSnapshot, context: StrategyEvaluationContext) -> StrategyDecision:
        row = dict(candidate.decision_inputs or {})
        params = _parameters(context)
        portfolio = dict(context.portfolio_state or {})
        positions = dict(portfolio.get("positions") or {})
        position = next((dict(value) for key, value in positions.items() if str(key).upper() == candidate.ticker), None)
        score = _float(row, "investment_score", "score", "combined_score", default=candidate.base_score or 0.0)
        quality = _float(row, "data_quality", "quality_score", "confidence_score", default=candidate.data_quality or 100.0)
        risk = _float(row, "risk_score", "risk", "combined_risk", default=40.0)
        price = _float(row, "price", "current_price", "last_price", default=candidate.price or 0.0)
        confidence = _float(row, "confidence_score", "confidence", default=quality)
        reasons: list[str] = []
        blockers: list[str] = []
        action = "SKIP"
        raw_decision = "SKIP"

        if position:
            average = _float(position, "average_price", default=price)
            highest = max(_float(position, "highest_price", default=price), price)
            if price <= 0:
                action, raw_decision = "HOLD", "HOLD"
                blockers.append("Mangler ny pris")
            elif price <= average * (1 - float(params.stop_loss_pct) / 100):
                action, raw_decision = "SELL", "SELL"
                reasons.append("STOP LOSS")
            elif price <= highest * (1 - float(params.trailing_stop_pct) / 100):
                action, raw_decision = "SELL", "SELL"
                reasons.append("TRAILING STOP")
            elif price >= average * (1 + float(params.take_profit_pct) / 100):
                action, raw_decision = "SELL", "SELL"
                reasons.append("TAKE PROFIT")
            elif score < float(params.score_exit_threshold):
                action, raw_decision = "SELL", "SELL"
                reasons.append(f"Investment Score falt til {score:.1f}")
            else:
                action, raw_decision = "HOLD", "HOLD"
                reasons.append("Ingen exitregel utløst")
        elif str(portfolio.get("status") or "ACTIVE").upper() != "ACTIVE":
            blockers.append(str(portfolio.get("pause_reason") or "Autonom portefølje er pauset"))
        elif score < float(params.minimum_investment_score):
            blockers.append(f"Score {score:.1f} under terskel")
        elif quality < float(params.minimum_data_quality):
            blockers.append(f"Datakvalitet {quality:.1f} under terskel")
        elif risk > float(params.maximum_risk_score):
            blockers.append(f"Risiko {risk:.1f} over grense")
        elif price <= 0:
            blockers.append("Mangler gyldig markedspris")
        elif len(positions) >= int(params.maximum_open_positions):
            blockers.append("Maks antall åpne posisjoner")
        else:
            action, raw_decision = "BUY", "BUY"
            reasons.append(f"Score {score:.1f}, risiko {risk:.1f}, datakvalitet {quality:.1f}")

        order_intent: dict[str, Any] = {}
        if action in {"BUY", "SELL"}:
            order_intent = {
                "side": action,
                "ticker": candidate.ticker,
                "status": "PROPOSED_ONLY",
                "reason": "Read-only parallellvurdering; produksjon utføres av eksisterende Autonomi-motor",
            }
        return StrategyDecision(
            decision_id=build_decision_id(
                run_id=context.run_id,
                strategy_version_id=str(self.version.get("version_id") or ""),
                candidate_snapshot_id=candidate.candidate_snapshot_id,
                purpose=context.purpose,
            ),
            run_id=context.run_id,
            strategy_family=str(self.version.get("strategy_family") or "autonomy"),
            strategy_id=str(self.version.get("strategy_id") or "autonomy_main"),
            strategy_version=str(self.version.get("strategy_version") or ""),
            strategy_version_id=str(self.version.get("version_id") or ""),
            strategy_status=str(self.version.get("status") or ""),
            execution_mode=str(self.version.get("execution_mode") or ""),
            ticker=candidate.ticker,
            action=action,
            raw_decision=raw_decision,
            score=score,
            confidence=confidence,
            reasons=tuple(reasons),
            blockers=tuple(blockers),
            market_snapshot_id=candidate.market_snapshot_id,
            candidate_snapshot_id=candidate.candidate_snapshot_id,
            snapshot_checksum=candidate.checksum,
            evaluated_at=context.evaluated_at,
            purpose=context.purpose,
            order_intent=order_intent,
            execution_authorized=False,
            metadata={
                "data_quality": quality,
                "risk_score": risk,
                "price": price,
                "read_only": True,
                "production_engine_unchanged": True,
            },
        )
