#!/usr/bin/env python3
"""Prepare v19.11.0 quality evidence and Strategy Lab attribution safely."""
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

OLD_QUALITY_VERSION_ID = "technical_quality_challenger@1.0.0"
NEW_QUALITY_VERSION_ID = "technical_quality_challenger@1.1.0"
PRODUCTION_VERSION_ID = "technical_benchmark@legacy-1.0.0"


def _snapshot_coverage(repositories) -> dict:
    snapshots = repositories.market_snapshots.list()
    candidates = [candidate for snapshot in snapshots for candidate in snapshot.get("candidates") or [] if isinstance(candidate, dict)]
    enriched = sum(1 for row in candidates if row.get("quality_evidence") or row.get("quality_coverage"))
    sufficient = sum(1 for row in candidates if bool((row.get("quality_coverage") or {}).get("sufficient_evidence")))
    return {
        "snapshot_count": len(snapshots),
        "candidate_count": len(candidates),
        "quality_enriched_candidates": enriched,
        "sufficient_evidence_candidates": sufficient,
        "historical_snapshots_rewritten": False,
    }


def migrate(*, dry_run: bool = False) -> dict:
    repositories = get_repository_registry()
    registry = StrategyRegistryService(repositories)
    production_before = registry.production_for_family("technical")
    old_before = registry.get(OLD_QUALITY_VERSION_ID)
    new_before = registry.get(NEW_QUALITY_VERSION_ID)
    result = {
        "release": "v19.11.0",
        "dry_run": dry_run,
        "production_before": (production_before or {}).get("version_id"),
        "old_challenger_before": (old_before or {}).get("status"),
        "new_challenger_before": (new_before or {}).get("status"),
        "would_pause_old_challenger": bool(old_before and old_before.get("status") in {"SHADOW", "CHALLENGER"}),
        "would_register_new_challenger": new_before is None,
        "snapshot_coverage": _snapshot_coverage(repositories),
        "existing_strategy_outcomes": len(repositories.strategy_outcomes.list()),
        "outcome_register_rewrites_snapshots": False,
        "errors": [],
    }
    if dry_run:
        return result
    try:
        registry.ensure_defaults()
        old = registry.get(OLD_QUALITY_VERSION_ID)
        if old and old.get("status") in {"SHADOW", "CHALLENGER"}:
            registry.set_status(OLD_QUALITY_VERSION_ID, "PAUSED", actor="migration_v19110", reason="Superseded by normalised evidence contract v1.1.0")
        new = registry.get(NEW_QUALITY_VERSION_ID)
        production_after = registry.production_for_family("technical")
        result.update({
            "old_challenger_after": (registry.get(OLD_QUALITY_VERSION_ID) or {}).get("status"),
            "new_challenger_registered": bool(new),
            "new_challenger_status": (new or {}).get("status"),
            "new_execution_mode": (new or {}).get("execution_mode"),
            "production_after": (production_after or {}).get("version_id"),
            "production_unchanged": (production_before or {}).get("version_id", PRODUCTION_VERSION_ID) == (production_after or {}).get("version_id"),
            "historical_snapshots_rewritten": False,
            "strategy_outcome_count": len(repositories.strategy_outcomes.list()),
            "outcome_register_rewrites_snapshots": False,
            "production_applied": False,
        })
        if result["production_after"] != PRODUCTION_VERSION_ID:
            result["errors"].append("Unexpected technical production binding")
    except Exception as exc:
        result["errors"].append(f"{type(exc).__name__}: {exc}")
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description="Prepare v19.11.0 Strategy Lab attribution and quality evidence.")
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
