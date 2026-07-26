#!/usr/bin/env python3
"""Bootstrap canonical production bindings for v19.12.0 without promoting anything."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from repositories.application import get_repository_registry
from services.strategy_registry_service import StrategyRegistryService


def migrate(*, dry_run: bool = False) -> dict:
    repositories = get_repository_registry()
    registry = StrategyRegistryService(repositories)
    status_production = {
        family: [row.get("version_id") for row in registry.list_versions(family=family, status="PRODUCTION")]
        for family in ("technical", "autonomy")
    }
    existing_bindings = {family: repositories.strategy_production_bindings.get(family) for family in ("technical", "autonomy")}
    result = {
        "release": "v19.12.0",
        "dry_run": dry_run,
        "status_production_before": status_production,
        "bindings_before": existing_bindings,
        "would_create_bindings": [family for family, row in existing_bindings.items() if not row],
        "would_bootstrap_defaults": not bool(repositories.strategy_versions.list()),
        "would_promote_strategy": False,
        "would_change_strategy_parameters": False,
        "would_rewrite_snapshots": False,
        "existing_promotions": len(repositories.strategy_promotions.list()),
        "errors": [],
    }
    if dry_run:
        if not repositories.strategy_versions.list():
            result["expected_default_bindings"] = {
                "technical": "technical_benchmark@legacy-1.0.0",
                "autonomy": "autonomy_main@1.0.0",
            }
            return result
        for family, versions in status_production.items():
            if not existing_bindings[family] and len(versions) != 1:
                result["errors"].append(f"Kan ikke etablere entydig binding for {family}: {versions}")
        return result
    try:
        registry.ensure_defaults()
        bindings = registry.ensure_production_bindings()
        result.update({
            "bindings_after": {row.get("strategy_family"): row for row in bindings},
            "technical_production_after": (registry.production_for_family("technical") or {}).get("version_id"),
            "autonomy_production_after": (registry.production_for_family("autonomy") or {}).get("version_id"),
            "promotion_applied": False,
            "strategy_parameters_changed": False,
            "historical_snapshots_rewritten": False,
        })
    except Exception as exc:
        result["errors"].append(f"{type(exc).__name__}: {exc}")
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description="Bootstrap v19.12.0 strategy promotion bindings safely.")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    result = migrate(dry_run=args.dry_run)
    text = json.dumps(result, ensure_ascii=False, indent=2, default=str)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(text, encoding="utf-8")
    print(text)
    return 1 if result.get("errors") else 0


if __name__ == "__main__":
    raise SystemExit(main())
