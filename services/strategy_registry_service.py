"""Persistent strategy registry and lifecycle service for v19.5.0."""
from __future__ import annotations

from dataclasses import replace
from typing import Any, Mapping

from app_version import APP_VERSION, AUTONOMY_POLICY_VERSION
from domain.strategy_versioning import (
    ExecutionMode,
    StrategyStatus,
    StrategyVersion,
    assert_transition_allowed,
    build_version_id,
    execution_mode_for_status,
    stable_config_checksum,
    utc_now_iso,
    validate_strategy_version,
)
from repositories.application import RepositoryRegistry, get_repository_registry


class StrategyRegistryError(RuntimeError):
    pass


class StrategyRegistryService:
    def __init__(self, repositories: RepositoryRegistry | None = None):
        self.repositories = repositories or get_repository_registry()
        self.versions = self.repositories.strategy_versions
        self.events = self.repositories.strategy_events

    def list_versions(self, *, family: str = "", status: str = "") -> list[dict[str, Any]]:
        rows = self.versions.list()
        family_key = str(family or "").strip().lower()
        status_key = str(status or "").strip().upper()
        if family_key:
            rows = [row for row in rows if str(row.get("strategy_family") or "").strip().lower() == family_key]
        if status_key:
            rows = [row for row in rows if str(row.get("status") or "").strip().upper() == status_key]
        return sorted(rows, key=lambda row: str(row.get("created_at") or ""), reverse=True)

    def get(self, version_id: str) -> dict[str, Any] | None:
        return self.versions.get(version_id)

    def production_for_family(self, family: str) -> dict[str, Any] | None:
        rows = self.list_versions(family=family, status=StrategyStatus.PRODUCTION.value)
        if len(rows) > 1:
            raise StrategyRegistryError(f"Flere produksjonsstrategier er registrert for {family}")
        return rows[0] if rows else None

    def _event(self, event_type: str, row: Mapping[str, Any], *, actor: str = "system", reason: str = "") -> None:
        self.events.append({
            "event_type": event_type,
            "version_id": row.get("version_id"),
            "strategy_id": row.get("strategy_id"),
            "strategy_family": row.get("strategy_family"),
            "strategy_version": row.get("strategy_version"),
            "status": row.get("status"),
            "execution_mode": row.get("execution_mode"),
            "actor": str(actor or "system"),
            "reason": str(reason or ""),
            "created_at": utc_now_iso(),
            "app_version": APP_VERSION,
        })

    def register(self, value: StrategyVersion | Mapping[str, Any], *, actor: str = "system", reason: str = "") -> dict[str, Any]:
        row = value.to_dict() if isinstance(value, StrategyVersion) else dict(value)
        row["version_id"] = row.get("version_id") or build_version_id(row.get("strategy_id", ""), row.get("strategy_version", ""))
        row["config_checksum"] = row.get("config_checksum") or stable_config_checksum(row.get("metadata") or {})
        row["created_at"] = row.get("created_at") or utc_now_iso()
        row["updated_at"] = utc_now_iso()
        validation = validate_strategy_version(row)
        if not validation["ok"]:
            raise StrategyRegistryError("; ".join(validation["errors"]))
        existing = self.get(row["version_id"])
        if existing and existing != row:
            raise StrategyRegistryError(f"Strategiversjonen finnes allerede: {row['version_id']}")
        if row["status"] == StrategyStatus.PRODUCTION.value:
            current = self.production_for_family(row["strategy_family"])
            if current and current.get("version_id") != row["version_id"]:
                raise StrategyRegistryError(f"Produksjonsbinding finnes allerede for {row['strategy_family']}")
        self.versions.upsert(row)
        self._event("STRATEGY_VERSION_REGISTERED", row, actor=actor, reason=reason)
        return row

    def ensure_defaults(self) -> list[dict[str, Any]]:
        defaults = [
            StrategyVersion(
                strategy_id="technical_benchmark",
                strategy_family="technical",
                display_name="Teknisk benchmark",
                strategy_version="legacy-1.0.0",
                parameter_version="paper-trading-rules-current",
                status=StrategyStatus.PRODUCTION.value,
                execution_mode=ExecutionMode.PAPER.value,
                implementation_version="v19.4.0",
                activated_at=utc_now_iso(),
                description="Dagens tekniske Paper Trading-strategi registrert uten regelendringer.",
                metadata={"source": "paper_trading", "rule_changes": False},
            ),
            StrategyVersion(
                strategy_id="technical_quality_challenger",
                strategy_family="technical",
                display_name="Technical Quality Challenger (v19.10 legacy)",
                strategy_version="1.0.0",
                parameter_version="technical-quality-1.0",
                status=StrategyStatus.PAUSED.value,
                execution_mode=ExecutionMode.DISABLED.value,
                implementation_version="v19.10.0",
                parent_version_id=build_version_id("technical_benchmark", "legacy-1.0.0"),
                description="Superseded read-only challenger retained for audit and historical reference.",
                metadata={
                    "source": "strategy_lab",
                    "strategy_kind": "technical_quality",
                    "production_applied": False,
                    "automatic_promotion": False,
                    "superseded_by": "technical_quality_challenger@1.1.0",
                    "quality_policy": {
                        "minimum_data_quality": 55.0,
                        "minimum_liquidity": 35.0,
                        "minimum_source_consensus": 40.0,
                        "minimum_evidence_components": 2,
                        "maximum_positive_adjustment": 1.0,
                        "maximum_negative_adjustment": 1.5,
                        "critical_event_blocks_entry": True,
                    },
                    "technical_parameters": {},
                },
            ),
            StrategyVersion(
                strategy_id="technical_quality_challenger",
                strategy_family="technical",
                display_name="Technical Quality Challenger",
                strategy_version="1.1.0",
                parameter_version="technical-quality-1.1",
                status=StrategyStatus.CHALLENGER.value,
                execution_mode=ExecutionMode.SHADOW_READ_ONLY.value,
                implementation_version=APP_VERSION,
                parent_version_id=build_version_id("technical_quality_challenger", "1.0.0"),
                description="Read-only challenger with normalised quality evidence, missing-data diagnostics and result attribution.",
                metadata={
                    "source": "strategy_lab",
                    "strategy_kind": "technical_quality",
                    "production_applied": False,
                    "automatic_promotion": False,
                    "quality_policy": {
                        "minimum_data_quality": 55.0,
                        "minimum_liquidity": 35.0,
                        "minimum_source_consensus": 40.0,
                        "minimum_evidence_components": 2,
                        "minimum_critical_evidence_components": 2,
                        "maximum_positive_adjustment": 1.0,
                        "maximum_negative_adjustment": 1.5,
                        "critical_event_blocks_entry": True,
                        "insufficient_evidence_blocks_buy": True,
                    },
                    "technical_parameters": {},
                },
            ),
            StrategyVersion(
                strategy_id="autonomy_main",
                strategy_family="autonomy",
                display_name="Autonomi hovedstrategi",
                strategy_version="1.0.0",
                parameter_version=AUTONOMY_POLICY_VERSION,
                status=StrategyStatus.PRODUCTION.value,
                execution_mode=ExecutionMode.PAPER.value,
                implementation_version="v19.4.0",
                activated_at=utc_now_iso(),
                description="Dagens autonome, teoretiske hovedstrategi registrert uten regelendringer.",
                metadata={"source": "autonomous_portfolio", "rule_changes": False},
            ),
        ]
        rows: list[dict[str, Any]] = []
        for default in defaults:
            version_id = build_version_id(default.strategy_id, default.strategy_version)
            existing = self.get(version_id)
            rows.append(existing or self.register(default, reason="versioned strategy bootstrap"))
        return rows

    def create_challenger(
        self,
        source_version_id: str,
        new_strategy_version: str,
        *,
        parameter_version: str = "",
        description: str = "",
        actor: str = "user",
        metadata: Mapping[str, Any] | None = None,
    ) -> dict[str, Any]:
        source = self.get(source_version_id)
        if not source:
            raise StrategyRegistryError(f"Ukjent kildestrategi: {source_version_id}")
        combined_metadata = dict(source.get("metadata") or {})
        combined_metadata.update(dict(metadata or {}))
        combined_metadata.update({"source_version_id": source_version_id, "production_applied": False})
        row = StrategyVersion(
            strategy_id=str(source["strategy_id"]),
            strategy_family=str(source["strategy_family"]),
            display_name=str(source["display_name"]),
            strategy_version=str(new_strategy_version),
            parameter_version=str(parameter_version or source.get("parameter_version") or "unchanged"),
            status=StrategyStatus.SHADOW.value,
            execution_mode=ExecutionMode.SHADOW_READ_ONLY.value,
            implementation_version=APP_VERSION,
            parent_version_id=source_version_id,
            description=str(description or "Shadow challenger"),
            metadata=combined_metadata,
        )
        return self.register(row, actor=actor, reason="Opprettet som skrivebeskyttet challenger")

    def set_status(self, version_id: str, target_status: str, *, actor: str = "user", reason: str = "") -> dict[str, Any]:
        current = self.get(version_id)
        if not current:
            raise StrategyRegistryError(f"Ukjent strategiversjon: {version_id}")
        try:
            assert_transition_allowed(current.get("status"), target_status)
        except ValueError as exc:
            raise StrategyRegistryError(str(exc)) from exc
        target = StrategyStatus(str(target_status).upper())
        updated = dict(current)
        updated["status"] = target.value
        updated["execution_mode"] = execution_mode_for_status(target).value
        updated["updated_at"] = utc_now_iso()
        if target == StrategyStatus.RETIRED:
            updated["retired_at"] = utc_now_iso()
        validation = validate_strategy_version(updated)
        if not validation["ok"]:
            raise StrategyRegistryError("; ".join(validation["errors"]))
        self.versions.upsert(updated)
        self._event("STRATEGY_STATUS_CHANGED", updated, actor=actor, reason=reason)
        return updated

    def decision_binding(self, family: str) -> dict[str, Any]:
        production = self.production_for_family(family)
        if not production:
            return {"strategy_family": family, "bound": False}
        return {
            "strategy_family": family,
            "bound": True,
            "version_id": production.get("version_id"),
            "strategy_id": production.get("strategy_id"),
            "strategy_version": production.get("strategy_version"),
            "parameter_version": production.get("parameter_version"),
            "implementation_version": production.get("implementation_version"),
            "config_checksum": production.get("config_checksum"),
        }


_default: StrategyRegistryService | None = None


def get_strategy_registry_service() -> StrategyRegistryService:
    global _default
    if _default is None:
        _default = StrategyRegistryService()
    return _default
