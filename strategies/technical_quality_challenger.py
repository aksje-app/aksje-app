"""Read-only Technical Quality Challenger for the common strategy interface."""
from __future__ import annotations

from typing import Any, Mapping
from dataclasses import replace

from domain.market_snapshot import CandidateSnapshot
from domain.strategy_contract import StrategyDecision, StrategyEvaluationContext, build_decision_id
from services.technical_quality_service import TechnicalQualityService, get_technical_quality_service


def _action(raw_decision: str, held: bool) -> str:
    raw = str(raw_decision or "").upper()
    if "BUY" in raw:
        return "BUY"
    if "SELL" in raw or "AVOID" in raw:
        return "SELL" if held else "AVOID"
    return "HOLD"


class TechnicalQualityChallengerStrategy:
    def __init__(self, version: Mapping[str, Any], quality_service: TechnicalQualityService | None = None):
        self.version = dict(version or {})
        self.quality_service = quality_service or get_technical_quality_service()

    def evaluate(self, candidate: CandidateSnapshot, context: StrategyEvaluationContext) -> StrategyDecision:
        metadata = dict(self.version.get("metadata") or {})
        decision_inputs = dict(candidate.decision_inputs or {})
        raw_base = decision_inputs.get("technical_score", decision_inputs.get("scanner_score", decision_inputs.get("score", candidate.base_score)))
        try:
            technical_base = float(raw_base)
            if technical_base > 10:
                technical_base = technical_base / 10.0
            decision_inputs["score"] = max(0.0, min(10.0, technical_base))
        except Exception:
            decision_inputs.setdefault("score", 5.0)
        evaluation_candidate = replace(candidate, decision_inputs=decision_inputs)
        result = self.quality_service.evaluate(
            evaluation_candidate,
            run_id=context.run_id,
            source=context.source,
            technical_parameters=dict(metadata.get("technical_parameters") or {}),
            quality_policy=dict(metadata.get("quality_policy") or {}),
            model_version=str(metadata.get("technical_model_version") or self.version.get("implementation_version") or "quality-1.0.0"),
            parameter_version=str(self.version.get("parameter_version") or "technical-quality-1.0"),
        )
        positions = dict((context.portfolio_state or {}).get("positions") or {})
        held = candidate.ticker in {str(key).upper() for key in positions}
        action = _action(result.get("decision", ""), held)
        order_intent: dict[str, Any] = {}
        if action in {"BUY", "SELL"}:
            order_intent = {
                "side": action,
                "ticker": candidate.ticker,
                "status": "PROPOSED_ONLY",
                "reason": "Strategy Lab challenger observation only",
            }
        return StrategyDecision(
            decision_id=build_decision_id(
                run_id=context.run_id,
                strategy_version_id=str(self.version.get("version_id") or ""),
                candidate_snapshot_id=candidate.candidate_snapshot_id,
                purpose=context.purpose,
            ),
            run_id=context.run_id,
            strategy_family=str(self.version.get("strategy_family") or "technical"),
            strategy_id=str(self.version.get("strategy_id") or "technical_quality_challenger"),
            strategy_version=str(self.version.get("strategy_version") or ""),
            strategy_version_id=str(self.version.get("version_id") or ""),
            strategy_status=str(self.version.get("status") or "CHALLENGER"),
            execution_mode=str(self.version.get("execution_mode") or "SHADOW_READ_ONLY"),
            ticker=candidate.ticker,
            action=action,
            raw_decision=str(result.get("decision") or ""),
            score=float(result.get("score") or 0.0),
            confidence=float(result.get("confidence") or 0.0),
            reasons=tuple(str(item) for item in (result.get("reasons") or [])),
            blockers=tuple(str(item) for item in (result.get("warnings") or [])),
            market_snapshot_id=candidate.market_snapshot_id,
            candidate_snapshot_id=candidate.candidate_snapshot_id,
            snapshot_checksum=candidate.checksum,
            evaluated_at=context.evaluated_at,
            purpose=context.purpose,
            order_intent=order_intent,
            execution_authorized=False,
            metadata={
                "technical_quality_result": result,
                "quality_adjustment": result.get("quality_adjustment"),
                "quality_component_count": result.get("quality_component_count"),
                "quality_blockers": result.get("quality_blockers"),
                "technical_base_score": result.get("technical_base_score"),
                "read_only": True,
                "strategy_role": "TECHNICAL_QUALITY_CHALLENGER",
                "production_benchmark_unchanged": True,
            },
        )
