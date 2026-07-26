"""Route Paper Trading decisions through the canonical production binding."""
from __future__ import annotations

from typing import Any, Mapping

from domain.market_snapshot import CandidateSnapshot
from domain.strategy_contract import StrategyEvaluationContext
from services.strategy_registry_service import StrategyRegistryService, get_strategy_registry_service
from services.technical_quality_service import TechnicalQualityService, get_technical_quality_service
from strategies.technical_quality_challenger import TechnicalQualityChallengerStrategy

PRODUCTION_STRATEGY_ROUTER_VERSION = "1.0"


class ProductionStrategyService:
    def __init__(self, registry: StrategyRegistryService | None = None, quality_service: TechnicalQualityService | None = None):
        self.registry = registry or get_strategy_registry_service()
        self.quality_service = quality_service or get_technical_quality_service()

    def evaluate_technical(
        self,
        candidate: CandidateSnapshot | Mapping[str, Any],
        base_decision: Mapping[str, Any],
        *,
        run_id: str,
        portfolio_state: Mapping[str, Any] | None = None,
    ) -> dict[str, Any]:
        candidate_obj = candidate if isinstance(candidate, CandidateSnapshot) else CandidateSnapshot.from_mapping(candidate)
        production = self.registry.production_for_family("technical") or {}
        version_id = str(production.get("version_id") or "technical_benchmark@legacy-1.0.0")
        if str(production.get("strategy_id") or "technical_benchmark") == "technical_benchmark":
            result = dict(base_decision or {})
            result.setdefault("production_strategy_version_id", version_id)
            result.setdefault("production_router_version", PRODUCTION_STRATEGY_ROUTER_VERSION)
            return result
        try:
            strategy = TechnicalQualityChallengerStrategy(production, self.quality_service)
            decision = strategy.evaluate(candidate_obj, StrategyEvaluationContext(
                run_id=run_id,
                source="paper_scanner_production_router",
                purpose="PAPER_PRODUCTION_DECISION",
                portfolio_state=dict(portfolio_state or {}),
                metadata={"production_router_version": PRODUCTION_STRATEGY_ROUTER_VERSION},
            )).to_dict()
            action = str(decision.get("action") or "HOLD").upper()
            legacy_signal = "BUY" if action == "BUY" else ("SELL" if action == "SELL" else ("AVOID" if action == "AVOID" else "HOLD / WAIT"))
            return {
                **dict(base_decision or {}),
                "decision": legacy_signal,
                "emoji": "✅" if action == "BUY" else ("❌" if action in {"SELL", "AVOID"} else "⏸"),
                "score": float(decision.get("score") or 0.0),
                "final_score": float(decision.get("score") or 0.0),
                "decision_score": float(decision.get("score") or 0.0),
                "confidence": int(round(float(decision.get("confidence") or 0.0))),
                "reasons": list(decision.get("reasons") or []),
                "warnings": list(decision.get("blockers") or []),
                "production_strategy_version_id": version_id,
                "production_strategy_decision_id": decision.get("decision_id"),
                "production_strategy_metadata": dict(decision.get("metadata") or {}),
                "production_router_version": PRODUCTION_STRATEGY_ROUTER_VERSION,
            }
        except Exception as exc:
            # Fail closed for new entries. Existing positions still pass HOLD to
            # auto_trade, whose independent stop-loss/take-profit checks remain active.
            return {
                **dict(base_decision or {}),
                "decision": "HOLD / WAIT",
                "emoji": "⏸",
                "score": 0.0,
                "final_score": 0.0,
                "decision_score": 0.0,
                "confidence": 0,
                "reasons": [],
                "warnings": [f"Produksjonsstrategi feilet lukket: {type(exc).__name__}: {str(exc)[:300]}"],
                "production_strategy_version_id": version_id,
                "production_router_error": f"{type(exc).__name__}: {str(exc)[:300]}",
                "production_router_version": PRODUCTION_STRATEGY_ROUTER_VERSION,
            }


_default: ProductionStrategyService | None = None


def get_production_strategy_service() -> ProductionStrategyService:
    global _default
    if _default is None:
        _default = ProductionStrategyService()
    return _default
