"""Technical benchmark implementation for the shared strategy interface."""
from __future__ import annotations

from typing import Any, Mapping
from dataclasses import replace

from domain.market_snapshot import CandidateSnapshot
from domain.strategy_contract import (
    StrategyDecision,
    StrategyEvaluationContext,
    build_decision_id,
)
from services.technical_signal_service import TechnicalSignalService, get_technical_signal_service


def _action(raw_decision: str, held: bool) -> str:
    raw = str(raw_decision or "").upper()
    if "BUY" in raw:
        return "BUY"
    if "SELL" in raw or "AVOID" in raw:
        return "SELL" if held else "AVOID"
    return "HOLD"


class TechnicalBenchmarkStrategy:
    def __init__(self, version: Mapping[str, Any], technical_service: TechnicalSignalService | None = None):
        self.version = dict(version or {})
        self.technical_service = technical_service or get_technical_signal_service()

    def evaluate(self, candidate: CandidateSnapshot, context: StrategyEvaluationContext) -> StrategyDecision:
        metadata = dict(self.version.get("metadata") or {})
        parameters = dict(metadata.get("technical_parameters") or metadata.get("parameter_overrides") or {})
        # Autonomi snapshots often carry 0-100 investment scores. The technical
        # service consumes the legacy 0-10 scale, so prefer an explicit
        # technical/scanner score and only normalise values above ten.
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
        result = self.technical_service.evaluate(
            evaluation_candidate,
            run_id=context.run_id,
            source=context.source,
            parameter_overrides=parameters,
            model_version=str(metadata.get("technical_model_version") or self.version.get("implementation_version") or "legacy-1.0.0"),
            parameter_version=str(self.version.get("parameter_version") or "paper-trading-rules-current"),
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
                "execution_mode": self.version.get("execution_mode"),
                "reason": "Parallell strategivurdering; ingen utførelse autorisert i v19.7.0",
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
            strategy_id=str(self.version.get("strategy_id") or "technical_benchmark"),
            strategy_version=str(self.version.get("strategy_version") or ""),
            strategy_version_id=str(self.version.get("version_id") or ""),
            strategy_status=str(self.version.get("status") or ""),
            execution_mode=str(self.version.get("execution_mode") or ""),
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
                "technical_result": result,
                "held_in_strategy_portfolio": held,
                "read_only": True,
                "strategy_role": "PRODUCTION_BENCHMARK" if self.version.get("status") == "PRODUCTION" else "PARALLEL_CHALLENGER",
            },
        )
