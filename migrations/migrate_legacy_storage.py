"""Non-destructive, idempotent migration of legacy JSON/JSONL into v19.2.0 storage.

The migrator never deletes or renames source files. Applied checksums are written
to a migration journal so repeating the same migration is safe.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from domain.persistence import MigrationResult
from repositories.application import get_repository_registry
from services.storage_service import StorageService

JOURNAL_KEY = "migration/v19.2.0_journal.json"

# Record collections get repository semantics and stable identifiers.
COLLECTION_MAPPINGS = {
    "report_archive.json": ("reports", "run_id"),
    "source_health_state.json": ("source_health", "source_id"),
    "run_trace_index.json": ("run_traces", "trace_id"),
    "scheduler_jobs.json": ("scheduler", "job_id"),
    "approvals.json": ("approvals", "approval_id"),
    "tasks.json": ("tasks", "task_id"),
    "portfolios.json": ("portfolios", "portfolio_id"),
}

# Major legacy singleton/list documents retain their established storage keys.
DOCUMENT_SUFFIX_MAPPINGS = {
    "app_settings.json": "settings/app_settings.json",
    "paper_portfolio.json": "paper_trading/portfolio.json",
    "autonomous_portfolio/parameters.json": "autonomous_portfolio/parameters.json",
    "autonomous_portfolio/portfolio.json": "autonomous_portfolio/portfolio.json",
    "autonomous_portfolio/trades.json": "autonomous_portfolio/trades.json",
    "autonomous_portfolio/decisions.json": "autonomous_portfolio/decisions.json",
    "autonomous_portfolio/notifications.json": "autonomous_portfolio/notifications.json",
    "autonomous_portfolio/performance.json": "autonomous_portfolio/performance.json",
    "autonomous_portfolio/equity_history.json": "autonomous_portfolio/equity_history.json",
    "autonomous_portfolio/learning_portfolio.json": "autonomous_portfolio/learning_portfolio.json",
    "autonomous_portfolio/learning_trades.json": "autonomous_portfolio/learning_trades.json",
    "autonomous_portfolio/learning_decisions.json": "autonomous_portfolio/learning_decisions.json",
    "controlled_learning/state.json": "controlled_learning/state.json",
    "controlled_learning/hypotheses.json": "controlled_learning/hypotheses.json",
    "controlled_learning/experiments.json": "controlled_learning/experiments.json",
    "controlled_learning/parameter_versions.json": "controlled_learning/parameter_versions.json",
    "controlled_learning/management_reports.json": "controlled_learning/management_reports.json",
    "controlled_learning/promotion_approvals.json": "controlled_learning/promotion_approvals.json",
    "adaptive_ranking/model_state.json": "adaptive_ranking/model_state.json",
    "adaptive_ranking/model_proposals.json": "adaptive_ranking/model_proposals.json",
    "adaptive_ranking/model_audit.json": "adaptive_ranking/model_audit.json",
    "market_intelligence/jobs.json": "market_intelligence/jobs.json",
    "market_intelligence/candidate_history.json": "market_intelligence/candidate_history.json",
    "market_intelligence/latest_run.json": "market_intelligence/latest_run.json",
    "market_intelligence/job_history.json": "market_intelligence/job_history.json",
    "market_intelligence/scheduler_health.json": "market_intelligence/scheduler_health.json",
    "operations/source_health_state.json": "operations/source_health_state.json",
    "operations/run_trace_index.json": "operations/run_trace_index.json",
    "autonomi_core/configuration_registry.json": "autonomi_core/configuration_registry.json",
}

EVENT_SUFFIX_MAPPINGS = {
    "autonomous_portfolio/audit.jsonl": "autonomous_portfolio/audit.jsonl",
    "controlled_learning/audit.jsonl": "controlled_learning/audit.jsonl",
    "market_intelligence/audit.jsonl": "market_intelligence/audit.jsonl",
    "operations/events.jsonl": "operations/events.jsonl",
    "operations/errors.jsonl": "operations/errors.jsonl",
    "operations/source_health.jsonl": "operations/source_health.jsonl",
    "operations/run_traces.jsonl": "operations/run_traces.jsonl",
}


def checksum(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _suffix(path: Path, mapping: dict[str, str]) -> str | None:
    normalized = path.as_posix().lower()
    matches = [(suffix, key) for suffix, key in mapping.items() if normalized.endswith(suffix.lower())]
    return max(matches, key=lambda item: len(item[0]))[1] if matches else None


def read_rows(path: Path) -> list[dict[str, Any]]:
    if path.suffix.lower() == ".jsonl":
        out: list[dict[str, Any]] = []
        for line in path.read_text(encoding="utf-8").splitlines():
            try:
                value = json.loads(line)
                if isinstance(value, dict):
                    out.append(dict(value))
            except Exception:
                continue
        return out
    value = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(value, list):
        return [dict(item) for item in value if isinstance(item, dict)]
    if isinstance(value, dict):
        if value and all(isinstance(item, dict) for item in value.values()):
            return [dict(item) for item in value.values()]
        return [dict(value)]
    return []


def _journal(storage: StorageService) -> dict[str, Any]:
    value = storage.read_json(JOURNAL_KEY, {})
    return dict(value) if isinstance(value, dict) else {}


def _record_journal(storage: StorageService, digest: str, payload: dict[str, Any]) -> None:
    journal = _journal(storage)
    journal[digest] = dict(payload)
    storage.write_json(JOURNAL_KEY, journal)


def migrate_file(path: Path, *, storage: StorageService, dry_run: bool = True) -> MigrationResult:
    path = Path(path)
    digest = checksum(path)
    if not dry_run and digest in _journal(storage):
        previous = _journal(storage)[digest]
        return MigrationResult(str(path), str(previous.get("target") or ""), 0, 0, 0, digest, False, True, "Allerede migrert")

    registry = get_repository_registry(storage)
    collection = COLLECTION_MAPPINGS.get(path.name)
    document_key = _suffix(path, DOCUMENT_SUFFIX_MAPPINGS)
    event_key = _suffix(path, EVENT_SUFFIX_MAPPINGS)

    if collection:
        repo_name, id_field = collection
        repo = getattr(registry, repo_name)
        rows = read_rows(path)
        normalized: list[dict[str, Any]] = []
        for index, row in enumerate(rows, 1):
            item = dict(row)
            if not item.get(id_field):
                for alt in ("id", "run_id", "trace_id", "source_id", "job_id", "task_id", "approval_id", "portfolio_id"):
                    if item.get(alt):
                        item[id_field] = item[alt]; break
            if not item.get(id_field):
                item[id_field] = f"legacy-{path.stem}-{index}"
            normalized.append(item)
        if not dry_run:
            existing = {str(item.get(id_field)): item for item in repo.list()}
            for item in normalized:
                existing[str(item[id_field])] = item
            repo.replace_all(existing.values())
            _record_journal(storage, digest, {"source": str(path), "target": repo_name, "rows": len(normalized)})
        return MigrationResult(str(path), repo_name, len(rows), 0 if dry_run else len(normalized), 0, digest, dry_run, True, "Validert" if dry_run else "Importert")

    if event_key:
        rows = read_rows(path)
        if not dry_run:
            existing = registry.events.list(event_key, limit=10_000_000)
            fingerprints = {json.dumps(row, sort_keys=True, default=str) for row in existing}
            merged = list(existing)
            for row in rows:
                signature = json.dumps(row, sort_keys=True, default=str)
                if signature not in fingerprints:
                    merged.append(row); fingerprints.add(signature)
            registry.events.replace_all(event_key, merged)
            _record_journal(storage, digest, {"source": str(path), "target": event_key, "rows": len(rows)})
        return MigrationResult(str(path), event_key, len(rows), 0 if dry_run else len(rows), 0, digest, dry_run, True, "Validert" if dry_run else "Importert")

    if document_key:
        value = json.loads(path.read_text(encoding="utf-8"))
        discovered = len(value) if isinstance(value, list) else 1
        if not dry_run:
            registry.documents.write(document_key, value)
            _record_journal(storage, digest, {"source": str(path), "target": document_key, "rows": discovered})
        return MigrationResult(str(path), document_key, discovered, 0 if dry_run else discovered, 0, digest, dry_run, True, "Validert" if dry_run else "Importert")

    return MigrationResult(str(path), "", 0, 0, 0, digest, dry_run, False, "Ingen trygg mapping for filen")


def discover(root: Path) -> list[Path]:
    output: list[Path] = []
    for path in root.rglob("*"):
        if not path.is_file() or path.suffix.lower() not in {".json", ".jsonl"}:
            continue
        if path.name in COLLECTION_MAPPINGS or _suffix(path, DOCUMENT_SUFFIX_MAPPINGS) or _suffix(path, EVENT_SUFFIX_MAPPINGS):
            output.append(path)
    return sorted(output)


def main() -> int:
    parser = argparse.ArgumentParser(description="Migrer eldre permanente JSON/JSONL-data ikke-destruktivt.")
    parser.add_argument("root", type=Path)
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--base-dir", type=Path, default=None)
    parser.add_argument("--database-url", default=None)
    parser.add_argument("--manifest", type=Path, default=Path("migration_manifest_v19.2.0.json"))
    args = parser.parse_args()
    storage = StorageService(base_dir=args.base_dir, database_url=args.database_url)
    results = [migrate_file(path, storage=storage, dry_run=not args.apply) for path in discover(args.root)]
    manifest = {
        "schema_version": "2.0", "dry_run": not args.apply,
        "source_root": str(args.root), "source_deleted": False,
        "results": [result.to_dict() for result in results],
    }
    args.manifest.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(manifest, ensure_ascii=False, indent=2))
    return 0 if all(result.ok for result in results) else 2


if __name__ == "__main__":
    raise SystemExit(main())
