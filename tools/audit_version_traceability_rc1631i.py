#!/usr/bin/env python3
"""Static and isolated-runtime release gate for the current version identity."""
from __future__ import annotations

import json
from pathlib import Path
from tempfile import TemporaryDirectory

from app_version import (
    APP_VERSION, AUTONOMY_POLICY_VERSION, AUTONOMY_STRATEGY_VERSION_ID,
    CONTROLLED_LEARNING_POLICY_VERSION, OPERATIONS_TELEMETRY_VERSION,
)
from repositories.application import RepositoryRegistry
from services.storage_service import StorageService
from services.strategy_account_service import StrategyAccountService
from services.strategy_registry_service import StrategyRegistryService


ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    errors: list[str] = []
    checks: list[str] = []

    def require(ok: bool, label: str) -> None:
        (checks if ok else errors).append(label)

    require(APP_VERSION == "v19.22.0-rc16.31r", "canonical app version")
    require(CONTROLLED_LEARNING_POLICY_VERSION == "v19.3.1", "controlled-learning contract")
    require(OPERATIONS_TELEMETRY_VERSION == "v19.2.0", "operations-telemetry contract")
    binding_source = (ROOT / "services/strategy_binding.py").read_text(encoding="utf-8")
    account_source = (ROOT / "services/strategy_account_service.py").read_text(encoding="utf-8")
    require('"implementation_version": "v19.4.0"' not in binding_source, "no stale binding fallback literal")
    require('or "v19.3.0"' not in account_source, "no stale account fallback literal")

    with TemporaryDirectory() as tmp:
        repositories = RepositoryRegistry(StorageService(base_dir=Path(tmp), mode="local", allow_local_fallback=True))
        registry = StrategyRegistryService(repositories)
        registry.ensure_defaults()
        production = registry.production_for_family("autonomy") or {}
        require(production.get("version_id") == AUTONOMY_STRATEGY_VERSION_ID, "canonical autonomy binding")
        require(production.get("implementation_version") == APP_VERSION, "autonomy implementation identity")
        require(production.get("parameter_version") == AUTONOMY_POLICY_VERSION, "autonomy policy identity")
        require(bool(production.get("config_checksum")), "autonomy config checksum")
        historical = registry.get("autonomy_main@1.0.0") or {}
        require(historical.get("implementation_version") == "v19.4.0", "historical version remains immutable")
        account = {row["account_id"]: row for row in StrategyAccountService(repositories, registry).ensure_defaults()}["autonomy_main"]
        require(account.get("strategy_version_id") == AUTONOMY_STRATEGY_VERSION_ID, "account follows binding")
        require(account.get("parameter_version") == AUTONOMY_POLICY_VERSION, "account follows policy")

    result = {"ok": not errors, "app_version": APP_VERSION, "checks": checks, "errors": errors}
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
