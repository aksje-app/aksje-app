from __future__ import annotations

from app_version import (
    APP_VERSION,
    AUTONOMY_POLICY_VERSION,
    AUTONOMY_STRATEGY_VERSION_ID,
    CONTROLLED_LEARNING_POLICY_VERSION,
    OPERATIONS_TELEMETRY_VERSION,
)
from repositories.application import RepositoryRegistry
from services.storage_service import StorageService
from services.strategy_account_service import StrategyAccountService
from services.strategy_registry_service import StrategyRegistryService


def _services(tmp_path):
    repositories = RepositoryRegistry(StorageService(base_dir=tmp_path, mode="local", allow_local_fallback=True))
    registry = StrategyRegistryService(repositories)
    accounts = StrategyAccountService(repositories, registry)
    return repositories, registry, accounts


def test_canonical_component_versions_match_runtime_modules():
    import controlled_parameter_learning
    import operational_telemetry

    assert APP_VERSION == "v19.22.0-rc16.31i"
    assert controlled_parameter_learning.VERSION == CONTROLLED_LEARNING_POLICY_VERSION == "v19.3.1"
    assert operational_telemetry.COMPONENT_VERSION == OPERATIONS_TELEMETRY_VERSION == "v19.2.0"


def test_default_autonomy_binding_and_account_migrate_without_history_rewrite(tmp_path):
    repositories, registry, accounts = _services(tmp_path)
    registry.ensure_defaults()

    production = registry.production_for_family("autonomy")
    assert production["version_id"] == AUTONOMY_STRATEGY_VERSION_ID
    assert production["implementation_version"] == APP_VERSION
    assert production["parameter_version"] == AUTONOMY_POLICY_VERSION
    assert production["config_checksum"]

    legacy = registry.get("autonomy_main@1.0.0")
    assert legacy is not None
    assert legacy["implementation_version"] == "v19.4.0"
    assert legacy["status"] == "SHADOW"

    account = {row["account_id"]: row for row in accounts.ensure_defaults()}["autonomy_main"]
    assert account["strategy_version_id"] == AUTONOMY_STRATEGY_VERSION_ID
    assert account["parameter_version"] == AUTONOMY_POLICY_VERSION

    events = repositories.strategy_events.list(limit=50)
    assert any(row.get("event_type") == "STRATEGY_BINDING_MIGRATED" for row in events)


def test_custom_autonomy_binding_is_never_overwritten(tmp_path):
    repositories, registry, _accounts = _services(tmp_path)
    registry.ensure_defaults()
    custom = dict(registry.get(AUTONOMY_STRATEGY_VERSION_ID))
    custom.update({
        "version_id": "autonomy_main@custom-2.0.0",
        "strategy_version": "custom-2.0.0",
        "status": "PRODUCTION",
        "execution_mode": "PAPER",
    })
    repositories.strategy_versions.upsert(custom)
    binding = dict(repositories.strategy_production_bindings.get("autonomy"))
    binding.update({"version_id": custom["version_id"], "state": "ACTIVE", "pending_version_id": ""})
    repositories.strategy_production_bindings.upsert(binding)

    recreated = StrategyRegistryService(repositories)
    recreated.ensure_defaults()
    assert recreated.production_for_family("autonomy")["version_id"] == custom["version_id"]


def test_legacy_sync_uses_bound_parameter_version(tmp_path):
    _repositories, registry, accounts = _services(tmp_path)
    registry.ensure_defaults()
    saved = accounts.sync_legacy_account(
        "autonomy_main", {"cash": 500000.0, "positions": {}},
        strategy_family="autonomy", strategy_id="autonomy_main",
        strategy_version_id=AUTONOMY_STRATEGY_VERSION_ID,
        display_name="Autonomi hovedstrategi", role="PRODUCTION", status="ACTIVE",
    )
    assert saved["parameter_version"] == AUTONOMY_POLICY_VERSION
