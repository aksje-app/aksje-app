"""Human-controlled strategy promotion and one-step rollback for v19.12.0.

The canonical production binding is a dedicated record. Status fields remain
human-readable mirrors. Promotion is never automatic and never authorises a
broker order; it only selects which already-versioned strategy Paper Trading
uses for future decisions.
"""
from __future__ import annotations

from dataclasses import replace
from typing import Any, Mapping

from app_version import APP_VERSION
from domain.strategy_promotion import (
    StrategyProductionBinding,
    StrategyPromotion,
    build_promotion_id,
    utc_now_iso,
)
from domain.strategy_versioning import ExecutionMode, StrategyStatus
from repositories.application import RepositoryRegistry, get_repository_registry
from services.strategy_registry_service import StrategyRegistryError, StrategyRegistryService

STRATEGY_PROMOTION_SERVICE_VERSION = "1.0"
DEFAULT_PROMOTION_GATES = {
    "minimum_outcome_pairs": 20,
    "minimum_outcome_coverage_pct": 60.0,
    "minimum_sufficient_evidence_pct": 80.0,
    "minimum_validation_outcome_samples": 10,
    "require_no_errors": True,
    "require_reliable_attribution": True,
    "require_non_negative_selection_delta": True,
}


class StrategyPromotionError(RuntimeError):
    pass


class StrategyPromotionService:
    def __init__(self, repositories: RepositoryRegistry | None = None, registry: StrategyRegistryService | None = None):
        self.repositories = repositories or get_repository_registry()
        self.registry = registry or StrategyRegistryService(self.repositories)
        self.promotions = self.repositories.strategy_promotions
        self.bindings = self.repositories.strategy_production_bindings
        self.approvals = self.repositories.strategy_lab_approvals
        self.experiments = self.repositories.strategy_lab_experiments
        self.runs = self.repositories.strategy_lab_runs

    def _clear_binding_cache(self) -> None:
        try:
            from services.strategy_binding import current_strategy_binding
            current_strategy_binding.cache_clear()
        except Exception:
            pass

    def current_binding(self, family: str) -> dict[str, Any] | None:
        self.registry.ensure_defaults()
        return self.bindings.get(str(family or "").strip().lower())

    def _attribution(self, run: Mapping[str, Any], target_version_id: str) -> dict[str, Any]:
        return next((dict(row) for row in run.get("result_attribution") or [] if str(row.get("challenger_version_id") or "") == target_version_id), {})

    def _metric(self, run: Mapping[str, Any], target_version_id: str) -> dict[str, Any]:
        return next((dict(row) for row in run.get("metrics") or [] if str(row.get("strategy_version_id") or "") == target_version_id), {})

    def preflight(self, approval_id: str, target_version_id: str, *, gates: Mapping[str, Any] | None = None) -> dict[str, Any]:
        policy = {**DEFAULT_PROMOTION_GATES, **dict(gates or {})}
        blockers: list[str] = []
        warnings: list[str] = []
        approval = self.approvals.get(approval_id)
        if not approval:
            return {"eligible": False, "blockers": ["Ukjent godkjenning"], "warnings": [], "gates": policy}
        if str(approval.get("status") or "") != "APPROVED_FOR_MANUAL_PROMOTION_REVIEW":
            blockers.append("Godkjenningen er ikke aktiv for promoteringsvurdering")
        experiment = self.experiments.get(str(approval.get("experiment_id") or "")) or {}
        run = self.runs.get(str(approval.get("lab_run_id") or experiment.get("latest_lab_run_id") or "")) or {}
        target = self.registry.get(target_version_id) or {}
        current = self.registry.production_for_family(str(target.get("strategy_family") or "technical")) or {}
        if not experiment:
            blockers.append("Eksperimentet finnes ikke")
        if not run:
            blockers.append("Lab-kjøringen finnes ikke")
        if not target:
            blockers.append("Målstrategien finnes ikke")
        challengers = {str(item) for item in experiment.get("challenger_version_ids") or []}
        if target_version_id not in challengers:
            blockers.append("Målstrategien inngår ikke i det godkjente eksperimentet")
        if str(target.get("status") or "") not in {StrategyStatus.SHADOW.value, StrategyStatus.CHALLENGER.value}:
            blockers.append("Målstrategien er ikke en aktiv skrivebeskyttet challenger")
        if str(target.get("execution_mode") or "") != ExecutionMode.SHADOW_READ_ONLY.value:
            blockers.append("Målstrategien er ikke skrivebeskyttet før promotering")
        baseline = str(experiment.get("baseline_version_id") or "")
        if not current or str(current.get("version_id") or "") != baseline:
            blockers.append("Produksjonsbaseline har endret seg siden eksperimentet ble opprettet")
        if str(target.get("strategy_family") or "") != str(current.get("strategy_family") or ""):
            blockers.append("Challenger og produksjonsbaseline tilhører ulike strategifamilier")
        if policy["require_no_errors"] and int(run.get("error_count") or 0) != 0:
            blockers.append("Lab-kjøringen inneholder feil")
        attribution = self._attribution(run, target_version_id)
        metric = self._metric(run, target_version_id)
        if not attribution:
            blockers.append("Resultatattribusjon mangler for challengeren")
        outcome_pairs = int(attribution.get("outcome_pairs") or 0)
        if outcome_pairs < int(policy["minimum_outcome_pairs"]):
            blockers.append(f"For få observerte utfall: {outcome_pairs} < {int(policy['minimum_outcome_pairs'])}")
        coverage = float(attribution.get("outcome_coverage_pct") or 0.0)
        if coverage < float(policy["minimum_outcome_coverage_pct"]):
            blockers.append(f"For lav utfallsdekning: {coverage:.1f} %")
        if policy["require_reliable_attribution"] and not bool(attribution.get("attribution_reliable")):
            blockers.append("Resultatattribusjonen er fortsatt foreløpig")
        evidence_pct = float(metric.get("sufficient_evidence_pct") or 0.0)
        if evidence_pct < float(policy["minimum_sufficient_evidence_pct"]):
            blockers.append(f"For lav evidensdekning: {evidence_pct:.1f} %")
        validation_samples = int(metric.get("validation_outcome_samples") or 0)
        if validation_samples < int(policy["minimum_validation_outcome_samples"]):
            blockers.append(f"For få valideringsutfall: {validation_samples}")
        delta = attribution.get("selection_return_delta_pct")
        if policy["require_non_negative_selection_delta"] and (delta is None or float(delta) < 0.0):
            blockers.append("Challenger har ikke dokumentert ikke-negativ seleksjonsforbedring")
        if int(attribution.get("missed_gains") or 0) > int(attribution.get("avoided_losses") or 0):
            warnings.append("Challengeren har filtrert flere gevinster enn tap i observasjonsperioden")
        return {
            "eligible": not blockers,
            "blockers": blockers,
            "warnings": warnings,
            "gates": policy,
            "approval_id": approval_id,
            "experiment_id": approval.get("experiment_id"),
            "lab_run_id": approval.get("lab_run_id"),
            "baseline_version_id": baseline,
            "current_production_version_id": current.get("version_id"),
            "target_version_id": target_version_id,
            "strategy_family": target.get("strategy_family"),
            "outcome_pairs": outcome_pairs,
            "outcome_coverage_pct": coverage,
            "sufficient_evidence_pct": evidence_pct,
            "validation_outcome_samples": validation_samples,
            "selection_return_delta_pct": delta,
            "checked_at": utc_now_iso(),
            "service_version": STRATEGY_PROMOTION_SERVICE_VERSION,
        }

    def _write_binding(
        self, family: str, version_id: str, *, previous_version_id: str, promotion_id: str,
        actor: str, reason: str, state: str = "ACTIVE", pending_version_id: str = "",
    ) -> dict[str, Any]:
        existing = self.bindings.get(family) or {}
        row = StrategyProductionBinding(
            binding_id=family,
            strategy_family=family,
            version_id=version_id,
            previous_version_id=previous_version_id,
            promotion_id=promotion_id,
            state=state,
            pending_version_id=pending_version_id,
            updated_by=actor,
            reason=reason,
            binding_revision=int(existing.get("binding_revision") or 0) + 1,
        ).to_dict()
        self.bindings.upsert(row)
        self._clear_binding_cache()
        return row

    def _production_row(self, row: Mapping[str, Any], *, production: bool, actor: str, reason: str, promotion_id: str) -> dict[str, Any]:
        updated = dict(row)
        updated["status"] = StrategyStatus.PRODUCTION.value if production else StrategyStatus.SHADOW.value
        updated["execution_mode"] = ExecutionMode.PAPER.value if production else ExecutionMode.SHADOW_READ_ONLY.value
        updated["updated_at"] = utc_now_iso()
        if production:
            updated["activated_at"] = utc_now_iso()
        metadata = dict(updated.get("metadata") or {})
        metadata.update({
            "production_applied": production,
            "automatic_promotion": False,
            "latest_promotion_id": promotion_id,
            "promotion_actor": actor,
            "promotion_reason": reason,
            "promotion_app_version": APP_VERSION,
        })
        updated["metadata"] = metadata
        return updated

    def promote(self, approval_id: str, target_version_id: str, *, actor: str, reason: str, confirmation: str) -> dict[str, Any]:
        if str(confirmation or "").strip().upper() != "PROMOTER":
            raise StrategyPromotionError("Skriv PROMOTER for å aktivere strategien i Paper Trading")
        if not str(reason or "").strip():
            raise StrategyPromotionError("Begrunnelse er påkrevd")
        check = self.preflight(approval_id, target_version_id)
        if not check.get("eligible"):
            raise StrategyPromotionError("; ".join(check.get("blockers") or ["Pre-flight feilet"]))
        approval = self.approvals.get(approval_id) or {}
        target = self.registry.get(target_version_id) or {}
        family = str(target.get("strategy_family") or "")
        previous = self.registry.production_for_family(family) or {}
        created_at = utc_now_iso()
        promotion_id = build_promotion_id(family, target_version_id, created_at)
        before_binding = self.bindings.get(family) or {}
        pending = StrategyPromotion(
            promotion_id=promotion_id,
            strategy_family=family,
            previous_version_id=str(previous.get("version_id") or ""),
            target_version_id=target_version_id,
            approval_id=approval_id,
            experiment_id=str(approval.get("experiment_id") or ""),
            lab_run_id=str(approval.get("lab_run_id") or ""),
            status="PENDING",
            actor=actor,
            reason=reason,
            created_at=created_at,
            preflight=check,
            previous_version_snapshot=previous,
            target_version_snapshot=target,
            production_binding_before=before_binding,
        ).to_dict()
        self.promotions.upsert(pending)
        try:
            self._write_binding(
                family, str(previous.get("version_id") or ""), previous_version_id=str(before_binding.get("previous_version_id") or ""),
                promotion_id=promotion_id, actor=actor, reason=reason, state="PENDING_PROMOTION", pending_version_id=target_version_id,
            )
            self.registry.versions.upsert(self._production_row(previous, production=False, actor=actor, reason=reason, promotion_id=promotion_id))
            self.registry.versions.upsert(self._production_row(target, production=True, actor=actor, reason=reason, promotion_id=promotion_id))
            binding = self._write_binding(
                family, target_version_id, previous_version_id=str(previous.get("version_id") or ""),
                promotion_id=promotion_id, actor=actor, reason=reason, state="ACTIVE", pending_version_id="",
            )
        except Exception as exc:
            if previous.get("version_id"):
                self._write_binding(family, str(previous.get("version_id")), previous_version_id=str(before_binding.get("previous_version_id") or ""), promotion_id=promotion_id, actor="system", reason="Kompensasjon etter mislykket promotering")
            self.registry.versions.upsert(dict(previous))
            self.registry.versions.upsert(dict(target))
            failed = dict(pending)
            failed.update({"status": "FAILED", "failure": f"{type(exc).__name__}: {exc}", "updated_at": utc_now_iso()})
            self.promotions.upsert(failed)
            raise StrategyPromotionError(f"Promotering feilet og ble kompensert: {exc}") from exc
        active = dict(pending)
        active.update({"status": "ACTIVE", "activated_at": utc_now_iso(), "production_binding_after": binding, "updated_at": utc_now_iso()})
        self.promotions.upsert(active)
        approval_row = dict(approval)
        approval_row.update({"status": "PROMOTED", "production_applied": True, "promotion_id": promotion_id, "promoted_at": utc_now_iso(), "updated_at": utc_now_iso()})
        self.approvals.upsert(approval_row)
        self.registry._event("STRATEGY_PROMOTED", self.registry.get(target_version_id) or target, actor=actor, reason=reason)
        return active

    def rollback(self, promotion_id: str, *, actor: str, reason: str, confirmation: str) -> dict[str, Any]:
        if str(confirmation or "").strip().upper() != "RULL TILBAKE":
            raise StrategyPromotionError("Skriv RULL TILBAKE for å gjenopprette forrige produksjonsstrategi")
        if not str(reason or "").strip():
            raise StrategyPromotionError("Rollback-begrunnelse er påkrevd")
        promotion = self.promotions.get(promotion_id)
        if not promotion or str(promotion.get("status") or "") != "ACTIVE":
            raise StrategyPromotionError("Promoteringen er ikke aktiv")
        family = str(promotion.get("strategy_family") or "")
        previous_id = str(promotion.get("previous_version_id") or "")
        target_id = str(promotion.get("target_version_id") or "")
        current = self.registry.production_for_family(family) or {}
        if str(current.get("version_id") or "") != target_id:
            raise StrategyPromotionError("Produksjonsbindingen har endret seg; automatisk rollback er stoppet")
        previous = self.registry.get(previous_id) or dict(promotion.get("previous_version_snapshot") or {})
        target = self.registry.get(target_id) or dict(promotion.get("target_version_snapshot") or {})
        if not previous:
            raise StrategyPromotionError("Forrige produksjonsversjon finnes ikke")
        try:
            self._write_binding(
                family, target_id, previous_version_id=previous_id, promotion_id=promotion_id, actor=actor, reason=reason,
                state="PENDING_ROLLBACK", pending_version_id=previous_id,
            )
            self.registry.versions.upsert(self._production_row(target, production=False, actor=actor, reason=reason, promotion_id=promotion_id))
            self.registry.versions.upsert(self._production_row(previous, production=True, actor=actor, reason=reason, promotion_id=promotion_id))
            binding = self._write_binding(
                family, previous_id, previous_version_id=target_id, promotion_id=promotion_id, actor=actor, reason=reason,
                state="ACTIVE", pending_version_id="",
            )
        except Exception as exc:
            self._write_binding(family, target_id, previous_version_id=previous_id, promotion_id=promotion_id, actor="system", reason="Kompensasjon etter mislykket rollback")
            raise StrategyPromotionError(f"Rollback feilet og produksjonsbindingen ble beholdt: {exc}") from exc
        updated = dict(promotion)
        updated.update({
            "status": "ROLLED_BACK",
            "rolled_back_at": utc_now_iso(),
            "rollback_actor": actor,
            "rollback_reason": reason,
            "rollback_binding": binding,
            "updated_at": utc_now_iso(),
        })
        self.promotions.upsert(updated)
        approval = self.approvals.get(str(promotion.get("approval_id") or ""))
        if approval:
            approval_row = dict(approval)
            approval_row.update({"status": "ROLLED_BACK_AFTER_PROMOTION", "production_applied": False, "rollback_at": utc_now_iso(), "updated_at": utc_now_iso()})
            self.approvals.upsert(approval_row)
        self.registry._event("STRATEGY_PROMOTION_ROLLED_BACK", self.registry.get(previous_id) or previous, actor=actor, reason=reason)
        return updated

    def recent_promotions(self, limit: int = 100) -> list[dict[str, Any]]:
        return sorted(self.promotions.list(), key=lambda row: str(row.get("updated_at") or row.get("created_at") or ""), reverse=True)[:max(0, int(limit))]


_default: StrategyPromotionService | None = None


def get_strategy_promotion_service() -> StrategyPromotionService:
    global _default
    if _default is None:
        _default = StrategyPromotionService()
    return _default
