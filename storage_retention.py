"""Conservative retention for reproducible runtime artefacts."""
from __future__ import annotations
from datetime import datetime, timezone
from typing import Any
from durable_runtime import read_json, write_json
from services.storage_service import get_storage_service
from storage_architecture import runtime_data_path

STATE_KEY = "maintenance/storage_retention.json"
STATE_PATH = runtime_data_path("maintenance", "storage_retention.json")
KV_LIMITS = {"operations/run_traces/": 500, "investment_pipeline/runs/": 120,
             "investment_pipeline/proposals/": 120, "market_intelligence/runs/": 90,
             "market_intelligence/summaries/": 90, "autonomous_orchestrator/runs/": 120,
             "autonomi_core/parallel_validation/": 120, "autonomi_core/learning_reporting/": 120,
             "full_replay/": 180}
JSONL_LIMITS = {"operations/run_traces.jsonl": 1000,
                "market_intelligence/job_history.jsonl": 1000}

def run_storage_retention() -> dict[str, Any]:
    storage = get_storage_service(); deleted: dict[str, int] = {}
    names = storage.list_json_names()
    for prefix, keep in KV_LIMITS.items():
        victims = sorted((n for n in names if n.startswith(prefix)), reverse=True)[max(1, keep):]
        for name in victims: storage.delete_json(name)
        if victims: deleted[prefix] = len(victims)
    trimmed: dict[str, int] = {}; logs = set(storage.list_jsonl_names())
    for name, keep in JSONL_LIMITS.items():
        if name in logs:
            rows = storage.read_jsonl(name, limit=keep); storage.replace_jsonl(name, rows); trimmed[name] = len(rows)
    state = {"state": "COMPLETED", "completed_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
             "deleted_keys": deleted, "retained_event_rows": trimmed,
             "protected": ["portfolio", "trades", "decisions", "settings", "audit"]}
    write_json(STATE_KEY, STATE_PATH, state); return state

def load_storage_retention_state() -> dict[str, Any]:
    value = read_json(STATE_KEY, STATE_PATH, {})
    return dict(value) if isinstance(value, dict) else {}
