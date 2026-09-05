"""Durable low-overhead breadcrumbs for scheduler/report OOM diagnosis.

Breadcrumbs are intentionally tiny and written *before* expensive phases so the
last durable marker survives a hard Render OOM kill. They are operational
telemetry only and never affect scoring, trading, or report decisions.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Mapping
import os

LATEST_KEY = "runtime/oom_breadcrumb_latest.json"
EVENTS_KEY = "runtime/oom_breadcrumb_events.jsonl"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds")


def _small(value: Any) -> Any:
    if value is None or isinstance(value, (bool, int, float)):
        return value
    if isinstance(value, str):
        return value[:300]
    if isinstance(value, Mapping):
        out: dict[str, Any] = {}
        for key, item in list(value.items())[:20]:
            if item is None or isinstance(item, (bool, int, float, str)):
                out[str(key)[:80]] = _small(item)
        return out
    if isinstance(value, (list, tuple)):
        return [_small(item) for item in list(value)[:12] if item is None or isinstance(item, (bool, int, float, str))]
    return str(type(value).__name__)


def mark_breadcrumb(stage: str, *, component: str = "scheduler", detail: Mapping[str, Any] | None = None) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "at": _now(),
        "stage": str(stage or "UNKNOWN")[:180],
        "component": str(component or "scheduler")[:80],
        "pid": os.getpid(),
        "runtime_role": str(os.getenv("AI_RUNTIME_ROLE", ""))[:80],
    }
    try:
        from runtime_memory import memory_snapshot
        payload["memory"] = memory_snapshot()
    except Exception as exc:
        payload["memory_error"] = f"{type(exc).__name__}: {str(exc)[:200]}"
    if detail:
        payload["detail"] = _small(detail)
    try:
        from services.storage_service import get_storage_service
        storage = get_storage_service()
        storage.write_json(LATEST_KEY, payload)
        try:
            storage.append_jsonl(EVENTS_KEY, payload)
        except Exception:
            pass
        payload["persisted"] = True
    except Exception as exc:
        payload["persisted"] = False
        payload["persistence_error"] = f"{type(exc).__name__}: {str(exc)[:240]}"
    # stdout is useful even if PostgreSQL is transiently unavailable.
    try:
        mem = payload.get("memory") if isinstance(payload.get("memory"), Mapping) else {}
        print(f"OOM_BREADCRUMB stage={payload['stage']} rss_mb={mem.get('process_rss_mb')} cgroup_mb={mem.get('cgroup_memory_current_mb')} persisted={payload.get('persisted')}", flush=True)
    except Exception:
        pass
    return payload
