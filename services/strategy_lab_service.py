"""Persistent read-only Strategy Lab for v19.10.0."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Mapping, Sequence

from domain.strategy_lab import (
    StrategyLabExperiment,
    StrategyLabMode,
    StrategyLabRun,
    StrategyLabStatus,
    build_experiment_id,
    build_lab_run_id,
    utc_now_iso,
    validate_experiment,
)
from repositories.application import RepositoryRegistry, get_repository_registry
from services.parallel_strategy_service import ParallelStrategyService
from services.strategy_registry_service import StrategyRegistryService

STRATEGY_LAB_SERVICE_VERSION = "1.0"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _future_return(candidate: Mapping[str, Any]) -> float | None:
    row = dict(candidate.get("decision_inputs") or {})
    for key in ("future_return_pct", "return_5d_pct", "actual_return_pct", "outcome_return_pct", "forward_return_pct"):
        try:
            value = row.get(key)
            if value is not None:
                return float(value)
        except Exception:
            pass
    return None


class StrategyLabError(RuntimeError):
    pass


class StrategyLabService:
    def __init__(
        self,
        repositories: RepositoryRegistry | None = None,
        registry: StrategyRegistryService | None = None,
        parallel: ParallelStrategyService | None = None,
    ):
        self.repositories = repositories or get_repository_registry()
        self.registry = registry or StrategyRegistryService(self.repositories)
        self.parallel = parallel or ParallelStrategyService(self.repositories, self.registry)
        self.experiments = self.repositories.strategy_lab_experiments
        self.runs = self.repositories.strategy_lab_runs
        self.approvals = self.repositories.strategy_lab_approvals

    def create_experiment(
        self,
        *,
        name: str,
        hypothesis: str,
        baseline_version_id: str,
        challenger_version_ids: Sequence[str],
        snapshot_ids: Sequence[str] | None = None,
        mode: str = StrategyLabMode.WALK_FORWARD.value,
        train_ratio: float = 0.70,
        actor: str = "user",
        metadata: Mapping[str, Any] | None = None,
    ) -> dict[str, Any]:
        created_at = utc_now_iso()
        baseline = self.registry.get(baseline_version_id)
        if not baseline:
            raise StrategyLabError("Unknown baseline strategy version")
        challengers = [str(item) for item in challenger_version_ids if str(item).strip()]
        if not challengers:
            raise StrategyLabError("At least one challenger is required")
        for version_id in challengers:
            row = self.registry.get(version_id)
            if not row:
                raise StrategyLabError(f"Unknown challenger: {version_id}")
            if str(row.get("status") or "") not in {"SHADOW", "CHALLENGER"}:
                raise StrategyLabError(f"Challenger is not active read-only: {version_id}")
        experiment = StrategyLabExperiment(
            experiment_id=build_experiment_id(name=name, baseline_version_id=baseline_version_id, created_at=created_at),
            name=str(name or "Strategy Lab experiment").strip(),
            hypothesis=str(hypothesis or "Compare challenger with production baseline").strip(),
            baseline_version_id=baseline_version_id,
            challenger_version_ids=tuple(challengers),
            snapshot_ids=tuple(str(item) for item in (snapshot_ids or []) if str(item).strip()),
            mode=str(mode or StrategyLabMode.WALK_FORWARD.value),
            train_ratio=float(train_ratio),
            status=StrategyLabStatus.READY.value,
            created_by=str(actor or "user"),
            created_at=created_at,
            updated_at=created_at,
            metadata={"production_applied": False, "execution_authorized": False, **dict(metadata or {})},
        )
        row = experiment.to_dict()
        validation = validate_experiment(row)
        if not validation["ok"]:
            raise StrategyLabError("; ".join(validation["errors"]))
        self.experiments.upsert(row)
        return row

    def ensure_default_quality_experiment(self) -> dict[str, Any] | None:
        self.registry.ensure_defaults()
        baseline = self.registry.get("technical_benchmark@legacy-1.0.0")
        challenger = self.registry.get("technical_quality_challenger@1.0.0")
        if not baseline or not challenger:
            return None
        existing = next((row for row in self.experiments.list() if row.get("metadata", {}).get("default_quality_experiment")), None)
        if existing:
            return existing
        return self.create_experiment(
            name="Technical Quality Challenger vs benchmark",
            hypothesis="Richer quality evidence improves entry selectivity without changing the pure technical production benchmark.",
            baseline_version_id=baseline["version_id"],
            challenger_version_ids=[challenger["version_id"]],
            mode=StrategyLabMode.WALK_FORWARD.value,
            actor="system",
            metadata={"default_quality_experiment": True},
        )

    def _selected_snapshots(self, experiment: Mapping[str, Any], snapshot_ids: Sequence[str] | None = None) -> list[dict[str, Any]]:
        selected = [str(item) for item in (snapshot_ids or experiment.get("snapshot_ids") or []) if str(item).strip()]
        if selected:
            rows = [self.repositories.market_snapshots.get(snapshot_id) for snapshot_id in selected]
            snapshots = [dict(row) for row in rows if isinstance(row, Mapping)]
        else:
            snapshots = [dict(row) for row in self.repositories.market_snapshots.list()]
        return sorted(snapshots, key=lambda row: str(row.get("captured_at") or ""))

    def _metrics(
        self,
        decisions: Sequence[Mapping[str, Any]],
        candidate_lookup: Mapping[str, Mapping[str, Any]],
        baseline_version_id: str,
        split_by_snapshot: Mapping[str, str],
    ) -> list[dict[str, Any]]:
        versions = sorted({str(row.get("strategy_version_id") or "") for row in decisions if row.get("strategy_version_id")})
        baseline_actions = {
            (str(row.get("market_snapshot_id") or ""), str(row.get("candidate_snapshot_id") or "")): str(row.get("action") or "")
            for row in decisions if str(row.get("strategy_version_id") or "") == baseline_version_id
        }
        metrics: list[dict[str, Any]] = []
        for version_id in versions:
            rows = [dict(row) for row in decisions if str(row.get("strategy_version_id") or "") == version_id]
            comparable = 0
            agreements = 0
            buy_returns: list[float] = []
            validation_buy_returns: list[float] = []
            quality_adjustments: list[float] = []
            quality_blocks = 0
            for row in rows:
                key = (str(row.get("market_snapshot_id") or ""), str(row.get("candidate_snapshot_id") or ""))
                if version_id != baseline_version_id and key in baseline_actions:
                    comparable += 1
                    agreements += int(str(row.get("action") or "") == baseline_actions[key])
                candidate = candidate_lookup.get(str(row.get("candidate_snapshot_id") or ""), {})
                outcome = _future_return(candidate)
                if str(row.get("action") or "") == "BUY" and outcome is not None:
                    buy_returns.append(outcome)
                    if split_by_snapshot.get(str(row.get("market_snapshot_id") or "")) == "VALIDATION":
                        validation_buy_returns.append(outcome)
                metadata = dict(row.get("metadata") or {})
                if metadata.get("quality_adjustment") is not None:
                    try:
                        quality_adjustments.append(float(metadata.get("quality_adjustment")))
                    except Exception:
                        pass
                quality_blocks += int(bool(metadata.get("quality_blockers")))
            metric = {
                "strategy_version_id": version_id,
                "strategy_id": rows[0].get("strategy_id") if rows else "",
                "strategy_version": rows[0].get("strategy_version") if rows else "",
                "status": rows[0].get("strategy_status") if rows else "",
                "decisions": len(rows),
                "buy": sum(1 for row in rows if row.get("action") == "BUY"),
                "hold": sum(1 for row in rows if row.get("action") == "HOLD"),
                "avoid": sum(1 for row in rows if row.get("action") in {"AVOID", "SELL"}),
                "errors": sum(1 for row in rows if row.get("action") == "ERROR"),
                "average_score": round(sum(float(row.get("score") or 0) for row in rows) / len(rows), 3) if rows else 0.0,
                "average_confidence": round(sum(float(row.get("confidence") or 0) for row in rows) / len(rows), 3) if rows else 0.0,
                "agreement_with_baseline_pct": round(agreements / comparable * 100, 2) if comparable else (100.0 if version_id == baseline_version_id else None),
                "outcome_samples": len(buy_returns),
                "average_return_when_buy_pct": round(sum(buy_returns) / len(buy_returns), 3) if buy_returns else None,
                "hit_rate_when_buy_pct": round(sum(1 for value in buy_returns if value > 0) / len(buy_returns) * 100, 2) if buy_returns else None,
                "validation_outcome_samples": len(validation_buy_returns),
                "validation_average_return_when_buy_pct": round(sum(validation_buy_returns) / len(validation_buy_returns), 3) if validation_buy_returns else None,
                "average_quality_adjustment": round(sum(quality_adjustments) / len(quality_adjustments), 3) if quality_adjustments else None,
                "quality_block_count": quality_blocks,
                "production_applied": False,
                "execution_authorized": False,
            }
            metrics.append(metric)
        return metrics

    def run_experiment(
        self,
        experiment_id: str,
        *,
        snapshot_ids: Sequence[str] | None = None,
        actor: str = "user",
    ) -> dict[str, Any]:
        experiment = self.experiments.get(experiment_id)
        if not experiment:
            raise StrategyLabError("Unknown Strategy Lab experiment")
        snapshots = self._selected_snapshots(experiment, snapshot_ids)
        if not snapshots:
            raise StrategyLabError("No market snapshots are available for replay")
        started_at = _now()
        running = dict(experiment)
        running.update({"status": StrategyLabStatus.RUNNING.value, "updated_at": started_at})
        self.experiments.upsert(running)
        version_ids = [str(experiment.get("baseline_version_id"))] + [str(item) for item in experiment.get("challenger_version_ids") or []]
        ratio = float(experiment.get("train_ratio") or 0.70)
        train_count = max(1, min(len(snapshots), int(round(len(snapshots) * ratio))))
        split_by_snapshot = {
            str(snapshot.get("snapshot_id") or ""): ("TRAIN" if index < train_count else "VALIDATION")
            for index, snapshot in enumerate(snapshots)
        }
        all_decisions: list[dict[str, Any]] = []
        errors = 0
        candidate_lookup: dict[str, dict[str, Any]] = {}
        for index, snapshot in enumerate(snapshots):
            snapshot_id = str(snapshot.get("snapshot_id") or "")
            for candidate in snapshot.get("candidates") or []:
                if isinstance(candidate, Mapping):
                    candidate_lookup[str(candidate.get("candidate_snapshot_id") or "")] = dict(candidate)
            result = self.parallel.evaluate_snapshot(
                snapshot,
                run_id=f"LAB-{experiment_id}-{index + 1}",
                source="strategy_lab_replay",
                purpose="STRATEGY_LAB_REPLAY",
                families=["technical", "autonomy"],
                version_ids=version_ids,
                context_metadata={
                    "strategy_lab_experiment_id": experiment_id,
                    "strategy_lab_split": split_by_snapshot.get(snapshot_id),
                    "read_only": True,
                },
            )
            rows = [dict(row) for row in result.get("decisions") or []]
            for row in rows:
                row["strategy_lab_experiment_id"] = experiment_id
                row["strategy_lab_split"] = split_by_snapshot.get(snapshot_id)
            all_decisions.extend(rows)
            errors += int(result.get("error_count") or 0)
        metrics = self._metrics(all_decisions, candidate_lookup, str(experiment.get("baseline_version_id") or ""), split_by_snapshot)
        completed_at = _now()
        run = StrategyLabRun(
            lab_run_id=build_lab_run_id(experiment_id=experiment_id, started_at=started_at),
            experiment_id=experiment_id,
            started_at=started_at,
            completed_at=completed_at,
            mode=str(experiment.get("mode") or StrategyLabMode.WALK_FORWARD.value),
            snapshot_count=len(snapshots),
            decision_count=len(all_decisions),
            error_count=errors,
            metrics=tuple(metrics),
            decisions=tuple(all_decisions),
            split={
                "train_snapshots": train_count,
                "validation_snapshots": max(0, len(snapshots) - train_count),
                "train_ratio": ratio,
                "time_ordered": True,
            },
            production_applied=False,
            execution_authorized=False,
            metadata={"actor": actor, "service_version": STRATEGY_LAB_SERVICE_VERSION, "automatic_promotion": False},
        )
        run_row = run.to_dict()
        self.runs.upsert(run_row)
        completed = dict(experiment)
        completed.update({
            "status": StrategyLabStatus.COMPLETED.value,
            "updated_at": completed_at,
            "latest_lab_run_id": run.lab_run_id,
            "latest_metrics": metrics,
            "production_applied": False,
        })
        self.experiments.upsert(completed)
        return run_row

    def submit_review(self, experiment_id: str, *, actor: str, reason: str) -> dict[str, Any]:
        experiment = self.experiments.get(experiment_id)
        if not experiment or not experiment.get("latest_lab_run_id"):
            raise StrategyLabError("Experiment must be completed before review")
        row = dict(experiment)
        row.update({"status": StrategyLabStatus.REVIEW.value, "updated_at": _now(), "review_reason": str(reason or "")})
        self.experiments.upsert(row)
        return row

    def approve(self, experiment_id: str, *, actor: str, reason: str, confirmation: str) -> dict[str, Any]:
        if str(confirmation or "").strip().upper() != "GODKJENN":
            raise StrategyLabError("Type GODKJENN to approve the lab result")
        experiment = self.experiments.get(experiment_id)
        if not experiment or str(experiment.get("status") or "") not in {StrategyLabStatus.REVIEW.value, StrategyLabStatus.COMPLETED.value}:
            raise StrategyLabError("Experiment is not ready for approval")
        created_at = _now()
        approval_id = f"LABAPP-{experiment_id}-{created_at}"
        approval = {
            "approval_id": approval_id,
            "experiment_id": experiment_id,
            "lab_run_id": experiment.get("latest_lab_run_id"),
            "status": "APPROVED_FOR_MANUAL_PROMOTION_REVIEW",
            "actor": str(actor or "user"),
            "reason": str(reason or ""),
            "created_at": created_at,
            "updated_at": created_at,
            "production_applied": False,
            "automatic_promotion": False,
            "rollback_available": True,
            "schema_version": "1.0",
        }
        self.approvals.upsert(approval)
        row = dict(experiment)
        row.update({"status": StrategyLabStatus.APPROVED.value, "updated_at": created_at, "latest_approval_id": approval_id, "production_applied": False})
        self.experiments.upsert(row)
        return approval

    def rollback_approval(self, approval_id: str, *, actor: str, reason: str, confirmation: str) -> dict[str, Any]:
        if str(confirmation or "").strip().upper() != "RULL TILBAKE":
            raise StrategyLabError("Type RULL TILBAKE to withdraw the approval")
        approval = self.approvals.get(approval_id)
        if not approval:
            raise StrategyLabError("Unknown approval")
        updated = dict(approval)
        updated.update({
            "status": "ROLLED_BACK",
            "rollback_actor": str(actor or "user"),
            "rollback_reason": str(reason or ""),
            "rollback_at": _now(),
            "updated_at": _now(),
            "production_applied": False,
        })
        self.approvals.upsert(updated)
        experiment = self.experiments.get(str(approval.get("experiment_id") or ""))
        if experiment:
            row = dict(experiment)
            row.update({"status": StrategyLabStatus.REVIEW.value, "updated_at": _now(), "production_applied": False})
            self.experiments.upsert(row)
        return updated

    def recent_experiments(self, limit: int = 100) -> list[dict[str, Any]]:
        return sorted(self.experiments.list(), key=lambda row: str(row.get("updated_at") or ""), reverse=True)[:max(0, int(limit))]

    def recent_runs(self, limit: int = 100) -> list[dict[str, Any]]:
        return sorted(self.runs.list(), key=lambda row: str(row.get("completed_at") or ""), reverse=True)[:max(0, int(limit))]

    def recent_approvals(self, limit: int = 100) -> list[dict[str, Any]]:
        return sorted(self.approvals.list(), key=lambda row: str(row.get("updated_at") or row.get("created_at") or ""), reverse=True)[:max(0, int(limit))]


_default: StrategyLabService | None = None


def get_strategy_lab_service() -> StrategyLabService:
    global _default
    if _default is None:
        _default = StrategyLabService()
    return _default
