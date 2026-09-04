"""Conservative, bounded retention for reproducible runtime artefacts."""
from __future__ import annotations

from datetime import datetime, timezone
import os
import time
from typing import Any

from durable_runtime import read_json, write_json
from services.storage_service import get_storage_service
from storage_architecture import runtime_data_path

STATE_KEY = "maintenance/storage_retention.json"
STATE_PATH = runtime_data_path("maintenance", "storage_retention.json")
KV_LIMITS = {
    "operations/run_traces/": 180, "investment_pipeline/runs/": 60,
    "investment_pipeline/proposals/": 90, "market_intelligence/runs/": 60,
    "market_intelligence/summaries/": 60, "autonomous_orchestrator/runs/": 90,
    "autonomi_core/parallel_validation/": 90, "autonomi_core/learning_reporting/": 90,
    "full_replay/": 60,
}
JSONL_LIMITS = {
    "operations/run_traces.jsonl": 400,
    "market_intelligence/job_history.jsonl": 300,
    "controlled_learning/outcome_audit.jsonl": 2000,
}
PROTECTED = ["portfolio", "trades", "positions", "decisions", "settings", "audit", "bounded_learning_observations"]


def _enabled() -> bool:
    return str(os.getenv("STORAGE_RETENTION_APPLY", "false")).strip().lower() in {"1", "true", "yes", "on"}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _save_state(state: dict[str, Any]) -> dict[str, Any]:
    write_json(STATE_KEY, STATE_PATH, state)
    return state


def run_storage_retention(*, apply: bool | None = None) -> dict[str, Any]:
    """Plan or execute one restart-safe, memory-bounded cleanup batch."""
    should_apply = _enabled() if apply is None else bool(apply)
    previous = load_storage_retention_state()
    storage = get_storage_service()
    health_obj = storage.health() if hasattr(storage, "health") else None
    health = health_obj.to_dict() if hasattr(health_obj, "to_dict") else {"ok": True, "backend": storage.backend() if hasattr(storage, "backend") else "test"}
    database_ready = bool(health.get("ok")) and str(health.get("backend") or "").lower() in {"postgres", "local"}
    if should_apply and not database_ready:
        return _save_state({
            "state": "BLOCKED_DATABASE", "completed_at": _now(), "apply_enabled": True,
            "database_health": health, "deleted_keys": {}, "deleted_this_batch": 0,
            "protected": PROTECTED,
        })

    before = storage.storage_usage_report()
    names = storage.list_json_names()
    max_items = max(1, min(100, int(os.getenv("STORAGE_RETENTION_BATCH_SIZE", "20") or 20)))
    max_seconds = max(5.0, min(120.0, float(os.getenv("STORAGE_RETENTION_TIME_BUDGET_SECONDS", "45") or 45)))
    started = time.monotonic()
    remaining_budget = max_items
    planned: dict[str, int] = {}
    deleted: dict[str, int] = {}
    pending_after_batch = 0

    for prefix, keep in KV_LIMITS.items():
        victims = sorted((name for name in names if name.startswith(prefix)), reverse=True)[max(1, keep):]
        if victims:
            planned[prefix] = len(victims)
        removed = 0
        if should_apply:
            for name in victims:
                if remaining_budget <= 0 or time.monotonic() - started >= max_seconds:
                    break
                storage.delete_json(name)
                removed += 1
                remaining_budget -= 1
            if removed:
                deleted[prefix] = removed
        pending_after_batch += max(0, len(victims) - removed) if should_apply else len(victims)

    trimmed: dict[str, int] = {}
    public_state = "DRY_RUN" if not should_apply else ("DEFERRED" if pending_after_batch else "PENDING")
    public_reports: dict[str, Any] = {"state": public_state}
    public_files: dict[str, Any] = {"state": public_state}
    # Never combine a KV backlog with JSONL rewrites and public-file pruning.
    if not pending_after_batch:
        logs = set(storage.list_jsonl_names())
        for name, keep in JSONL_LIMITS.items():
            if name in logs:
                rows = storage.read_jsonl(name, limit=keep)
                if should_apply:
                    storage.replace_jsonl(name, rows)
                trimmed[name] = len(rows)
        if should_apply:
            from public_report_store import prune_expired_public_files, prune_expired_public_reports
            public_reports = prune_expired_public_reports()
            public_files = prune_expired_public_files()

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
            "status": "GROWING" if daily > 0 else "STABLE_OR_SHRINKING", "sample_days": round(elapsed_days, 2),
            "delta_bytes": delta, "estimated_daily_growth_bytes": daily,
            "estimated_days_to_capacity": round(remaining / daily, 1) if daily > 0 and remaining > 0 else None,
        }
    except Exception:
        pass

    state_name = "PARTIAL" if should_apply and pending_after_batch else ("COMPLETED" if should_apply else "DRY_RUN")
    return _save_state({
        "state": state_name, "completed_at": completed.isoformat(timespec="seconds"), "apply_enabled": should_apply,
        "planned_deleted_keys": planned, "deleted_keys": deleted, "deleted_this_batch": sum(deleted.values()),
        "pending_after_batch": pending_after_batch, "batch_size": max_items, "time_budget_seconds": max_seconds,
        "retained_event_rows": trimmed, "public_reports": public_reports, "public_files": public_files,
        "usage_before": before, "usage_after": after, "capacity_trend": trend,
        "database_health": health, "protected": PROTECTED,
    })


def load_storage_retention_state() -> dict[str, Any]:
    value = read_json(STATE_KEY, STATE_PATH, {})
    return dict(value) if isinstance(value, dict) else {}
