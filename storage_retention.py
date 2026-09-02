"""Conservative retention for reproducible runtime artefacts."""
from __future__ import annotations
from datetime import datetime, timezone
import os
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

def _enabled() -> bool:
    return str(os.getenv("STORAGE_RETENTION_APPLY", "false")).strip().lower() in {"1", "true", "yes", "on"}


def run_storage_retention(*, apply: bool | None = None) -> dict[str, Any]:
    """Plan bounded cleanup; mutate only after explicit production opt-in."""
    should_apply = _enabled() if apply is None else bool(apply)
    previous = load_storage_retention_state()
    storage = get_storage_service(); before = storage.storage_usage_report(); deleted: dict[str, int] = {}
    planned: dict[str, int] = {}
    names = storage.list_json_names()
    for prefix, keep in KV_LIMITS.items():
        victims = sorted((n for n in names if n.startswith(prefix)), reverse=True)[max(1, keep):]
        if victims: planned[prefix] = len(victims)
        if should_apply:
            for name in victims: storage.delete_json(name)
            if victims: deleted[prefix] = len(victims)
    trimmed: dict[str, int] = {}; logs = set(storage.list_jsonl_names())
    for name, keep in JSONL_LIMITS.items():
        if name in logs:
            rows = storage.read_jsonl(name, limit=keep)
            if should_apply: storage.replace_jsonl(name, rows)
            trimmed[name] = len(rows)
    from public_report_store import prune_expired_public_files, prune_expired_public_reports
    public_reports = prune_expired_public_reports() if should_apply else {"state": "DRY_RUN"}
    public_files = prune_expired_public_files() if should_apply else {"state": "DRY_RUN"}
    after = storage.storage_usage_report()
    completed = datetime.now(timezone.utc)
    previous_usage = previous.get("usage_before") if isinstance(previous.get("usage_before"), dict) else {}
    trend: dict[str, Any] = {"status": "PENDING_SECOND_SAMPLE"}
    try:
        previous_at = datetime.fromisoformat(str(previous.get("completed_at") or "").replace("Z", "+00:00"))
        elapsed_days = max((completed - previous_at.astimezone(timezone.utc)).total_seconds() / 86400.0, 1 / 24)
        delta = int(before.get("database_bytes") or 0) - int(previous_usage.get("database_bytes") or 0)
        daily = round(delta / elapsed_days)
        remaining = int(before.get("capacity_bytes") or 0) - int(before.get("database_bytes") or 0)
        trend = {
            "status": "GROWING" if daily > 0 else "STABLE_OR_SHRINKING",
            "sample_days": round(elapsed_days, 2), "delta_bytes": delta,
            "estimated_daily_growth_bytes": daily,
            "estimated_days_to_capacity": round(remaining / daily, 1) if daily > 0 and remaining > 0 else None,
        }
    except Exception:
        pass
    state = {"state": "COMPLETED" if should_apply else "DRY_RUN", "completed_at": completed.isoformat(timespec="seconds"),
             "apply_enabled": should_apply, "planned_deleted_keys": planned, "deleted_keys": deleted, "retained_event_rows": trimmed,
             "public_reports": public_reports, "public_files": public_files, "usage_before": before, "usage_after": after,
             "capacity_trend": trend,
             "protected": ["portfolio", "trades", "positions", "decisions", "settings", "audit",
                           "bounded_learning_observations"]}
    write_json(STATE_KEY, STATE_PATH, state); return state

def load_storage_retention_state() -> dict[str, Any]:
    value = read_json(STATE_KEY, STATE_PATH, {})
    return dict(value) if isinstance(value, dict) else {}
