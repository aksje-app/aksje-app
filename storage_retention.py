"""Conservative retention for reproducible runtime artefacts."""
from __future__ import annotations
from datetime import datetime, timezone
from typing import Any
from durable_runtime import read_json, write_json
from services.storage_service import get_storage_service
from storage_architecture import runtime_data_path

STATE_KEY = "maintenance/storage_retention.json"
STATE_PATH = runtime_data_path("maintenance", "storage_retention.json")
KV_LIMITS = {"operations/run_traces/": 180, "investment_pipeline/runs/": 60,
             "investment_pipeline/proposals/": 90, "market_intelligence/runs/": 60,
             "market_intelligence/summaries/": 60, "autonomous_orchestrator/runs/": 90,
             "autonomi_core/parallel_validation/": 90, "autonomi_core/learning_reporting/": 90,
             "full_replay/": 60}
JSONL_LIMITS = {"operations/run_traces.jsonl": 400,
                "market_intelligence/job_history.jsonl": 300}

def run_storage_retention() -> dict[str, Any]:
    storage = get_storage_service(); before = storage.storage_usage_report(); deleted: dict[str, int] = {}
    names = storage.list_json_names()
    for prefix, keep in KV_LIMITS.items():
        victims = sorted((n for n in names if n.startswith(prefix)), reverse=True)[max(1, keep):]
        for name in victims: storage.delete_json(name)
        if victims: deleted[prefix] = len(victims)
    trimmed: dict[str, int] = {}; logs = set(storage.list_jsonl_names())
    for name, keep in JSONL_LIMITS.items():
        if name in logs:
            rows = storage.read_jsonl(name, limit=keep); storage.replace_jsonl(name, rows); trimmed[name] = len(rows)
    from public_report_store import prune_expired_public_files, prune_expired_public_reports
    public_reports = prune_expired_public_reports()
    public_files = prune_expired_public_files()
    after = storage.storage_usage_report()
    state = {"state": "COMPLETED", "completed_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
             "deleted_keys": deleted, "retained_event_rows": trimmed,
             "public_reports": public_reports, "public_files": public_files, "usage_before": before, "usage_after": after,
             "protected": ["portfolio", "trades", "positions", "decisions", "settings", "audit",
                           "bounded_learning_observations"]}
    write_json(STATE_KEY, STATE_PATH, state); return state

def load_storage_retention_state() -> dict[str, Any]:
    value = read_json(STATE_KEY, STATE_PATH, {})
    return dict(value) if isinstance(value, dict) else {}
