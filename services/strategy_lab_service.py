"""Persistent read-only Strategy Lab with comparison and attribution (v19.11.0)."""
from __future__ import annotations

from collections import Counter, defaultdict
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
from services.strategy_outcome_service import (
    PRIMARY_ATTRIBUTION_HORIZON,
    StrategyOutcomeService,
)

STRATEGY_LAB_SERVICE_VERSION = "1.2"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _future_return(
    candidate: Mapping[str, Any],
    *,
    candidate_snapshot_id: str = "",
    outcome_lookup: Mapping[str, Mapping[str, Any]] | None = None,
) -> float | None:
    observed = (outcome_lookup or {}).get(str(candidate_snapshot_id or ""))
    if isinstance(observed, Mapping):
        try:
            value = observed.get("return_pct")
            if value is not None:
                return float(value)
        except Exception:
            pass
    row = dict(candidate.get("decision_inputs") or {})
    for key in ("future_return_pct", "return_5d_pct", "actual_return_pct", "outcome_return_pct", "forward_return_pct"):
        try:
            value = row.get(key)
            if value is not None:
                return float(value)
        except Exception:
            pass
    return None


def _decision_key(row: Mapping[str, Any]) -> tuple[str, str]:
    return str(row.get("market_snapshot_id") or ""), str(row.get("candidate_snapshot_id") or "")


def _quality_result(row: Mapping[str, Any]) -> dict[str, Any]:
    metadata = dict(row.get("metadata") or {})
    result = metadata.get("technical_quality_result")
    return dict(result) if isinstance(result, Mapping) else {}


def _is_buy(row: Mapping[str, Any]) -> bool:
    return str(row.get("action") or "").upper() == "BUY"


def _mean(values: Sequence[float]) -> float | None:
    return round(sum(values) / len(values), 4) if values else None


class StrategyLabError(RuntimeError):
    pass


class StrategyLabService:
    def __init__(
        self,
        repositories: RepositoryRegistry | None = None,
        registry: StrategyRegistryService | None = None,
        parallel: ParallelStrategyService | None = None,
        outcomes: StrategyOutcomeService | None = None,
    ):
        self.repositories = repositories or get_repository_registry()
        self.registry = registry or StrategyRegistryService(self.repositories)
        self.parallel = parallel or ParallelStrategyService(self.repositories, self.registry)
        self.outcomes = outcomes or StrategyOutcomeService(self.repositories)
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
        challenger = self.registry.get("technical_quality_challenger@1.1.0")
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

    def _quality_diagnostics(self, decisions: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
        component_counts: dict[str, Counter] = defaultdict(Counter)
        blocker_counts: Counter = Counter()
        blocker_combinations: Counter = Counter()
        missing_counts: Counter = Counter()
        invalid_counts: Counter = Counter()
        sufficient = 0
        insufficient = 0
        quality_rows = 0
        for row in decisions:
            result = _quality_result(row)
            if not result:
                continue
            quality_rows += 1
            is_sufficient = bool(result.get("quality_evidence_sufficient"))
            sufficient += int(is_sufficient)
            insufficient += int(not is_sufficient)
            for diagnosis in result.get("quality_diagnostics") or []:
                if not isinstance(diagnosis, Mapping):
                    continue
                component = str(diagnosis.get("component") or "unknown")
                status = str(diagnosis.get("status") or "UNKNOWN")
                threshold_status = str(diagnosis.get("threshold_status") or status)
                component_counts[component][status] += 1
                if threshold_status != status:
                    component_counts[component][threshold_status] += 1
            codes = [str(code) for code in result.get("quality_blocker_codes") or [] if str(code)]
            for code in codes:
                blocker_counts[code] += 1
            if codes:
                blocker_combinations[" + ".join(sorted(codes))] += 1
            for name in result.get("quality_missing_components") or []:
                missing_counts[str(name)] += 1
            for name in result.get("quality_invalid_components") or []:
                invalid_counts[str(name)] += 1
        components = []
        for component in sorted(component_counts):
            counts = component_counts[component]
            components.append({
                "component": component,
                "available": counts.get("AVAILABLE", 0),
                "missing": counts.get("MISSING", 0),
                "invalid": counts.get("INVALID", 0),
                "below_threshold": counts.get("BELOW_THRESHOLD", 0),
                "pass": counts.get("PASS", 0),
                "evaluated": quality_rows,
            })
        return {
            "quality_decisions": quality_rows,
            "sufficient_evidence_count": sufficient,
            "insufficient_evidence_count": insufficient,
            "sufficient_evidence_pct": round(sufficient / quality_rows * 100, 2) if quality_rows else 0.0,
            "components": components,
            "blocker_counts": [{"code": code, "count": count} for code, count in blocker_counts.most_common()],
            "blocker_combinations": [{"combination": code, "count": count} for code, count in blocker_combinations.most_common()],
            "missing_components": [{"component": key, "count": count} for key, count in missing_counts.most_common()],
            "invalid_components": [{"component": key, "count": count} for key, count in invalid_counts.most_common()],
        }

    def _result_attribution(
        self,
        decisions: Sequence[Mapping[str, Any]],
        candidate_lookup: Mapping[str, Mapping[str, Any]],
        baseline_version_id: str,
        outcome_lookup: Mapping[str, Mapping[str, Any]] | None = None,
    ) -> list[dict[str, Any]]:
        baseline = {_decision_key(row): dict(row) for row in decisions if str(row.get("strategy_version_id") or "") == baseline_version_id}
        challengers = sorted({str(row.get("strategy_version_id") or "") for row in decisions if row.get("strategy_version_id") and str(row.get("strategy_version_id")) != baseline_version_id})
        out: list[dict[str, Any]] = []
        for version_id in challengers:
            rows = {_decision_key(row): dict(row) for row in decisions if str(row.get("strategy_version_id") or "") == version_id}
            filtered: list[float] = []
            added: list[float] = []
            baseline_buy_returns: list[float] = []
            challenger_buy_returns: list[float] = []
            avoided_losses = missed_gains = added_wins = added_losses = 0
            both_buy = both_not_buy = disagreements = outcome_pairs = 0
            blocker_outcomes: dict[str, list[float]] = defaultdict(list)
            component_delta_totals: dict[str, list[float]] = defaultdict(list)
            for key, base_row in baseline.items():
                challenger_row = rows.get(key)
                if not challenger_row:
                    continue
                base_buy = _is_buy(base_row)
                challenger_buy = _is_buy(challenger_row)
                disagreements += int(base_buy != challenger_buy)
                both_buy += int(base_buy and challenger_buy)
                both_not_buy += int(not base_buy and not challenger_buy)
                candidate = candidate_lookup.get(key[1], {})
                outcome = _future_return(candidate, candidate_snapshot_id=key[1], outcome_lookup=outcome_lookup)
                if outcome is not None:
                    outcome_pairs += 1
                    if base_buy:
                        baseline_buy_returns.append(outcome)
                    if challenger_buy:
                        challenger_buy_returns.append(outcome)
                    if base_buy and not challenger_buy:
                        filtered.append(outcome)
                        avoided_losses += int(outcome < 0)
                        missed_gains += int(outcome > 0)
                        result = _quality_result(challenger_row)
                        for code in result.get("quality_blocker_codes") or []:
                            blocker_outcomes[str(code)].append(outcome)
                    elif not base_buy and challenger_buy:
                        added.append(outcome)
                        added_wins += int(outcome > 0)
                        added_losses += int(outcome < 0)
                result = _quality_result(challenger_row)
                for component in result.get("quality_components") or []:
                    if isinstance(component, Mapping) and component.get("delta") is not None:
                        try:
                            component_delta_totals[str(component.get("component"))].append(float(component.get("delta")))
                        except Exception:
                            pass
            out.append({
                "challenger_version_id": version_id,
                "baseline_version_id": baseline_version_id,
                "comparable_decisions": len(set(baseline).intersection(rows)),
                "decision_disagreements": disagreements,
                "both_buy_count": both_buy,
                "both_not_buy_count": both_not_buy,
                "baseline_buys_filtered": len(filtered),
                "avoided_losses": avoided_losses,
                "missed_gains": missed_gains,
                "filtered_average_return_pct": _mean(filtered),
                "challenger_added_buys": len(added),
                "added_wins": added_wins,
                "added_losses": added_losses,
                "added_average_return_pct": _mean(added),
                "baseline_buy_average_return_pct": _mean(baseline_buy_returns),
                "challenger_buy_average_return_pct": _mean(challenger_buy_returns),
                "selection_return_delta_pct": round((_mean(challenger_buy_returns) or 0.0) - (_mean(baseline_buy_returns) or 0.0), 4) if baseline_buy_returns and challenger_buy_returns else None,
                "outcome_pairs": outcome_pairs,
                "outcome_coverage_pct": round(outcome_pairs / max(1, len(set(baseline).intersection(rows))) * 100, 2),
                "attribution_reliable": outcome_pairs >= 20,
                "blocker_outcomes": [
                    {"blocker_code": code, "samples": len(values), "average_return_pct": _mean(values), "losses": sum(1 for value in values if value < 0), "gains": sum(1 for value in values if value > 0)}
                    for code, values in sorted(blocker_outcomes.items())
                ],
                "component_attribution": [
                    {"component": name, "samples": len(values), "average_score_delta": _mean(values)}
                    for name, values in sorted(component_delta_totals.items())
                ],
                "production_applied": False,
                "execution_authorized": False,
            })
        return out

    def _metrics(
        self,
        decisions: Sequence[Mapping[str, Any]],
        candidate_lookup: Mapping[str, Mapping[str, Any]],
        baseline_version_id: str,
        split_by_snapshot: Mapping[str, str],
        outcome_lookup: Mapping[str, Mapping[str, Any]] | None = None,
    ) -> list[dict[str, Any]]:
        versions = sorted({str(row.get("strategy_version_id") or "") for row in decisions if row.get("strategy_version_id")})
        baseline_actions = {_decision_key(row): str(row.get("action") or "") for row in decisions if str(row.get("strategy_version_id") or "") == baseline_version_id}
        metrics: list[dict[str, Any]] = []
        for version_id in versions:
            rows = [dict(row) for row in decisions if str(row.get("strategy_version_id") or "") == version_id]
            comparable = agreements = quality_blocks = sufficient = insufficient = 0
            buy_returns: list[float] = []
            validation_buy_returns: list[float] = []
            quality_adjustments: list[float] = []
            for row in rows:
                key = _decision_key(row)
                if version_id != baseline_version_id and key in baseline_actions:
                    comparable += 1
                    agreements += int(str(row.get("action") or "") == baseline_actions[key])
                candidate = candidate_lookup.get(str(row.get("candidate_snapshot_id") or ""), {})
                outcome = _future_return(candidate, candidate_snapshot_id=str(row.get("candidate_snapshot_id") or ""), outcome_lookup=outcome_lookup)
                if _is_buy(row) and outcome is not None:
                    buy_returns.append(outcome)
                    if split_by_snapshot.get(str(row.get("market_snapshot_id") or "")) == "VALIDATION":
                        validation_buy_returns.append(outcome)
                result = _quality_result(row)
                if result:
                    quality_blocks += int(bool(result.get("quality_blockers")))
                    sufficient += int(bool(result.get("quality_evidence_sufficient")))
                    insufficient += int(not bool(result.get("quality_evidence_sufficient")))
                    if result.get("quality_adjustment") is not None:
                        try:
                            quality_adjustments.append(float(result.get("quality_adjustment")))
                        except Exception:
                            pass
            metrics.append({
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
                "average_return_when_buy_pct": _mean(buy_returns),
                "hit_rate_when_buy_pct": round(sum(1 for value in buy_returns if value > 0) / len(buy_returns) * 100, 2) if buy_returns else None,
                "validation_outcome_samples": len(validation_buy_returns),
                "validation_average_return_when_buy_pct": _mean(validation_buy_returns),
                "average_quality_adjustment": _mean(quality_adjustments),
                "quality_block_count": quality_blocks,
                "sufficient_evidence_count": sufficient,
                "insufficient_evidence_count": insufficient,
                "sufficient_evidence_pct": round(sufficient / max(1, sufficient + insufficient) * 100, 2) if sufficient + insufficient else None,
                "production_applied": False,
                "execution_authorized": False,
            })
        return metrics

    def run_experiment(
        self,
        experiment_id: str,
        *,
        snapshot_ids: Sequence[str] | None = None,
        actor: str = "user",
        settle_outcomes: bool = False,
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
        split_by_snapshot = {str(snapshot.get("snapshot_id") or ""): ("TRAIN" if index < train_count else "VALIDATION") for index, snapshot in enumerate(snapshots)}
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
                context_metadata={"strategy_lab_experiment_id": experiment_id, "strategy_lab_split": split_by_snapshot.get(snapshot_id), "read_only": True},
            )
            rows = [dict(row) for row in result.get("decisions") or []]
            for row in rows:
                row["strategy_lab_experiment_id"] = experiment_id
                row["strategy_lab_split"] = split_by_snapshot.get(snapshot_id)
            all_decisions.extend(rows)
            errors += int(result.get("error_count") or 0)
        baseline_version_id = str(experiment.get("baseline_version_id") or "")
        outcome_settlement = {
            "requested": bool(settle_outcomes),
            "created": 0,
            "existing": 0,
            "unavailable": 0,
            "error_count": 0,
            "horizons": [],
        }
        if settle_outcomes:
            outcome_settlement = {"requested": True, **self.outcomes.settle_snapshots(snapshots)}
        outcome_lookup = self.outcomes.lookup(horizon=PRIMARY_ATTRIBUTION_HORIZON)
        selected_candidate_ids = {str(key) for key in candidate_lookup if str(key)}
        observed_candidate_ids = selected_candidate_ids.intersection(outcome_lookup)
        outcome_coverage = {
            "primary_horizon_sessions": PRIMARY_ATTRIBUTION_HORIZON,
            "selected_candidates": len(selected_candidate_ids),
            "observed_candidates": len(observed_candidate_ids),
            "missing_outcomes": max(0, len(selected_candidate_ids) - len(observed_candidate_ids)),
            "coverage_pct": round(len(observed_candidate_ids) / max(1, len(selected_candidate_ids)) * 100, 2),
            "lookahead_used_in_decision": False,
        }
        metrics = self._metrics(all_decisions, candidate_lookup, baseline_version_id, split_by_snapshot, outcome_lookup)
        diagnostics = self._quality_diagnostics(all_decisions)
        attribution = self._result_attribution(all_decisions, candidate_lookup, baseline_version_id, outcome_lookup)
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
            split={"train_snapshots": train_count, "validation_snapshots": max(0, len(snapshots) - train_count), "train_ratio": ratio, "time_ordered": True},
            production_applied=False,
            execution_authorized=False,
            metadata={"actor": actor, "service_version": STRATEGY_LAB_SERVICE_VERSION, "automatic_promotion": False, "lookahead_used": False, "outcome_horizon_sessions": PRIMARY_ATTRIBUTION_HORIZON},
        )
        run_row = run.to_dict()
        run_row["quality_diagnostics"] = diagnostics
        run_row["result_attribution"] = attribution
        run_row["outcome_settlement"] = outcome_settlement
        run_row["outcome_coverage"] = outcome_coverage
        run_row["attribution_summary"] = {
            "strategies_compared": len(attribution),
            "outcome_samples": sum(int(row.get("outcome_pairs") or 0) for row in attribution),
            "reliable_comparisons": sum(1 for row in attribution if row.get("attribution_reliable")),
            "lookahead_used": False,
        }
        self.runs.upsert(run_row)
        completed = dict(experiment)
        completed.update({
            "status": StrategyLabStatus.COMPLETED.value,
            "updated_at": completed_at,
            "latest_lab_run_id": run.lab_run_id,
            "latest_metrics": metrics,
            "latest_quality_diagnostics": diagnostics,
            "latest_result_attribution": attribution,
            "latest_outcome_coverage": outcome_coverage,
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
        if not str(reason or "").strip():
            raise StrategyLabError("Begrunnelse er påkrevd for godkjenning")
        experiment = self.experiments.get(experiment_id)
        if not experiment or str(experiment.get("status") or "") not in {StrategyLabStatus.REVIEW.value, StrategyLabStatus.COMPLETED.value}:
            raise StrategyLabError("Experiment is not ready for approval")
        created_at = _now()
        approval_id = f"LABAPP-{experiment_id}-{created_at}"
        approval = {
            "approval_id": approval_id,
            "experiment_id": experiment_id,
            "lab_run_id": experiment.get("latest_lab_run_id"),
            "baseline_version_id": experiment.get("baseline_version_id"),
            "challenger_version_ids": list(experiment.get("challenger_version_ids") or []),
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
        if bool(approval.get("production_applied")) or str(approval.get("status") or "") == "PROMOTED":
            raise StrategyLabError("Godkjenningen er allerede promotert. Bruk produksjons-rollback, ikke trekk tilbake godkjenningen.")
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
