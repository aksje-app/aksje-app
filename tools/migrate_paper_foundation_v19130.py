#!/usr/bin/env python3
"""Dry-run, backup, migrate and reconcile legacy Paper state for v19.13.0."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Mapping

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from services.paper_migration_service import PaperMigrationService
from storage_architecture import runtime_data_path


def _json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


def load_legacy(service: PaperMigrationService, source_file: Path | None = None) -> tuple[dict[str, Any] | None, str]:
    if source_file:
        value = _json(source_file)
        return (dict(value), f"file:{source_file}") if isinstance(value, Mapping) else (None, f"invalid:{source_file}")
    value = service.repositories.documents.read("paper_trading/portfolio.json", default=None)
    if isinstance(value, Mapping):
        return dict(value), "document:paper_trading/portfolio.json"
    for path in (PROJECT_ROOT / "paper_portfolio.json", runtime_data_path("paper_portfolio.json")):
        value = _json(path)
        if isinstance(value, Mapping):
            return dict(value), f"file:{path}"
    return None, "missing"


def main() -> int:
    parser = argparse.ArgumentParser(description="v19.13.0 Paper Migration Foundation")
    parser.add_argument("--source-file", type=Path)
    parser.add_argument("--output-dir", type=Path, default=Path("migration_output_v19130"))
    parser.add_argument("--migrate", action="store_true", help="Utfør migrering. Uten flagget kjøres kun dry-run.")
    parser.add_argument("--confirm", default="")
    parser.add_argument("--reason", default="")
    args = parser.parse_args()
    service = PaperMigrationService()
    legacy, source = load_legacy(service, args.source_file)
    if legacy is None:
        print(json.dumps({"ok": False, "error": "Fant ingen gyldig legacy Paper-state", "source": source}, ensure_ascii=False, indent=2))
        return 2
    if args.migrate:
        result = service.migrate(legacy, source=source, output_dir=args.output_dir, confirmation=args.confirm, reason=args.reason)
    else:
        result = service.inspect(legacy, source=source)
    print(json.dumps(result, ensure_ascii=False, indent=2, default=str))
    return 0 if result.get("ok", True) else 1


if __name__ == "__main__":
    raise SystemExit(main())
