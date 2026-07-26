#!/usr/bin/env python3
"""Register v19.10.0 Strategy Lab repositories and quality challenger safely."""
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

QUALITY_VERSION_ID = "technical_quality_challenger@1.0.0"


def migrate(*, dry_run: bool = False) -> dict:
    repositories = get_repository_registry()
    registry = StrategyRegistryService(repositories)
    before = registry.get(QUALITY_VERSION_ID)
    result = {
        "dry_run": dry_run,
        "quality_challenger_before": bool(before),
        "would_register_quality_challenger": before is None,
        "strategy_lab_experiment_count": len(repositories.strategy_lab_experiments.list()),
        "strategy_lab_run_count": len(repositories.strategy_lab_runs.list()),
        "strategy_lab_approval_count": len(repositories.strategy_lab_approvals.list()),
        "errors": [],
    }
    if dry_run:
        return result
    try:
        registry.ensure_defaults()
        challenger = registry.get(QUALITY_VERSION_ID)
        result.update({
            "quality_challenger_registered": bool(challenger),
            "quality_challenger_status": (challenger or {}).get("status"),
            "execution_mode": (challenger or {}).get("execution_mode"),
            "production_applied": False,
        })
    except Exception as exc:
        result["errors"].append(f"{type(exc).__name__}: {exc}")
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description="Prepare Strategy Lab and Technical Quality Challenger for v19.10.0.")
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
