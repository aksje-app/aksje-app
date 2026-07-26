"""Read-only parallel strategy runner for v19.7.0.

All eligible strategy versions evaluate the same immutable MarketSnapshot.
The runner persists comparable decisions but has no execution dependency and
cannot mutate any strategy portfolio.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Mapping, Sequence

from domain.market_snapshot import CandidateSnapshot, MarketSnapshot, validate_market_snapshot
from domain.strategy_contract import (
    StrategyDecision,
    StrategyEvaluationContext,
    StrategyRunResult,
    build_decision_id,
    build_strategy_run_id,
    validate_strategy_decision,
)
from repositories.application import RepositoryRegistry, get_repository_registry
from services.strategy_registry_service import StrategyRegistryService, get_strategy_registry_service
from services.market_snapshot_service import MarketSnapshotService
from services.technical_signal_service import TechnicalSignalService, get_technical_signal_service
from strategies import AutonomyStrategy, TechnicalBenchmarkStrategy

ACTIVE_PARALLEL_STATUSES = {"PRODUCTION", "SHADOW", "CHALLENGER"}
PARALLEL_STRATEGY_SERVICE_VERSION = "1.0"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class ParallelStrategyService:
    def __init__(
        self,
        repositories: RepositoryRegistry | None = None,
        registry: StrategyRegistryService | None = None,
        technical_service: TechnicalSignalService | None = None,
    ):
        self.repositories = repositories or get_repository_registry()
        self.registry = registry or StrategyRegistryService(self.repositories)
        self.technical_service = technical_service or TechnicalSignalService(MarketSnapshotService(self.repositories))
        self.decisions = self.repositories.strategy_decisions
        self.runs = self.repositories.strategy_runs

    def eligible_versions(self, families: Sequence[str] | None = None) -> list[dict[str, Any]]:
        self.registry.ensure_defaults()
        allowed = {str(item).strip().lower() for item in (families or []) if str(item).strip()}
        rows = [row for row in self.registry.list_versions() if str(row.get("status") or "").upper() in ACTIVE_PARALLEL_STATUSES]
        if allowed:
            rows = [row for row in rows if str(row.get("strategy_family") or "").lower() in allowed]
        return sorted(rows, key=lambda row: (
            str(row.get("strategy_family") or ""),
            0 if str(row.get("status") or "").upper() == "PRODUCTION" else 1,
            str(row.get("version_id") or ""),
        ))

    def _implementation(self, version: Mapping[str, Any]):
        family = str(version.get("strategy_family") or "").lower()
        if family == "technical":
            return TechnicalBenchmarkStrategy(version, self.technical_service)
        if family == "autonomy":
            return AutonomyStrategy(version)
        raise ValueError(f"Ingen strategiimplementasjon for familie {family}")

    def _error_decision(
        self,
        version: Mapping[str, Any],
        candidate: CandidateSnapshot,
        context: StrategyEvaluationContext,
        exc: Exception,
    ) -> StrategyDecision:
        return StrategyDecision(
            decision_id=build_decision_id(
                run_id=context.run_id,
                strategy_version_id=str(version.get("version_id") or ""),
                candidate_snapshot_id=candidate.candidate_snapshot_id,
                purpose=context.purpose,
            ),
            run_id=context.run_id,
            strategy_family=str(version.get("strategy_family") or "unknown"),
            strategy_id=str(version.get("strategy_id") or "unknown"),
            strategy_version=str(version.get("strategy_version") or "unknown"),
            strategy_version_id=str(version.get("version_id") or "unknown"),
            strategy_status=str(version.get("status") or ""),
            execution_mode=str(version.get("execution_mode") or ""),
            ticker=candidate.ticker,
            action="ERROR",
            raw_decision="ERROR",
            score=0.0,
            confidence=0.0,
            reasons=(),
            blockers=(f"{type(exc).__name__}: {str(exc)[:500]}",),
            market_snapshot_id=candidate.market_snapshot_id,
            candidate_snapshot_id=candidate.candidate_snapshot_id,
            snapshot_checksum=candidate.checksum,
            evaluated_at=context.evaluated_at,
            purpose=context.purpose,
            execution_authorized=False,
            error=f"{type(exc).__name__}: {str(exc)[:500]}",
            metadata={"isolated_failure": True, "read_only": True},
        )

    def evaluate_snapshot(
        self,
        snapshot: MarketSnapshot | Mapping[str, Any],
        *,
        run_id: str = "",
        source: str = "parallel_strategy_service",
        purpose: str = "PARALLEL_COMPARISON",
        portfolio_states: Mapping[str, Mapping[str, Any]] | None = None,
        families: Sequence[str] | None = None,
        context_metadata: Mapping[str, Any] | None = None,
    ) -> dict[str, Any]:
        row = snapshot.to_dict() if isinstance(snapshot, MarketSnapshot) else dict(snapshot or {})
        validation = validate_market_snapshot(row)
        if not validation["ok"]:
            raise ValueError("; ".join(validation["errors"]))
        run_id = str(run_id or row.get("run_id") or row.get("snapshot_id") or "PARALLEL")
        started_at = _now()
        versions = self.eligible_versions(families)
        candidates = [CandidateSnapshot.from_mapping(item) for item in (row.get("candidates") or [])]
        results: list[dict[str, Any]] = []
        errors = 0
        portfolio_states = dict(portfolio_states or {})

        for version in versions:
            family = str(version.get("strategy_family") or "").lower()
            strategy = self._implementation(version)
            context = StrategyEvaluationContext(
                run_id=run_id,
                source=source,
                purpose=purpose,
                portfolio_state=dict(portfolio_states.get(family) or {}),
                metadata={
                    "parallel_strategy_service_version": PARALLEL_STRATEGY_SERVICE_VERSION,
                    **dict(context_metadata or {}),
                },
            )
            for candidate in candidates:
                try:
                    decision = strategy.evaluate(candidate, context)
                except Exception as exc:
                    errors += 1
                    decision = self._error_decision(version, candidate, context, exc)
                decision_row = decision.to_dict()
                check = validate_strategy_decision(decision_row)
                if not check["ok"]:
                    errors += 1
                    decision_row["action"] = "ERROR"
                    decision_row["raw_decision"] = "ERROR"
                    decision_row["error"] = "; ".join(check["errors"])
                    decision_row["blockers"] = list(decision_row.get("blockers") or []) + check["errors"]
                    decision_row["execution_authorized"] = False
                self.decisions.upsert(decision_row)
                results.append(decision_row)

        completed_at = _now()
        run_result = StrategyRunResult(
            strategy_run_id=build_strategy_run_id(run_id=run_id, market_snapshot_id=str(row.get("snapshot_id") or ""), source=source),
            run_id=run_id,
            source=source,
            market_snapshot_id=str(row.get("snapshot_id") or ""),
            started_at=started_at,
            completed_at=completed_at,
            strategy_count=len(versions),
            candidate_count=len(candidates),
            decision_count=len(results),
            error_count=errors,
            decisions=tuple(results),
            metadata={
                "purpose": purpose,
                "read_only": True,
                "execution_authorized": False,
                "families": sorted({str(v.get("strategy_family") or "") for v in versions}),
                "service_version": PARALLEL_STRATEGY_SERVICE_VERSION,
            },
        )
        run_row = run_result.to_dict()
        self.runs.upsert(run_row)
        return run_row

    def recent_runs(self, limit: int = 20) -> list[dict[str, Any]]:
        return sorted(self.runs.list(), key=lambda row: str(row.get("completed_at") or ""), reverse=True)[: max(0, int(limit))]

    def recent_decisions(self, limit: int = 500) -> list[dict[str, Any]]:
        return sorted(self.decisions.list(), key=lambda row: str(row.get("evaluated_at") or ""), reverse=True)[: max(0, int(limit))]


_default: ParallelStrategyService | None = None


def get_parallel_strategy_service() -> ParallelStrategyService:
    global _default
    if _default is None:
        _default = ParallelStrategyService()
    return _default
