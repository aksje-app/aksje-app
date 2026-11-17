"""Durable low-overhead breadcrumbs for scheduler/report OOM diagnosis.

Breadcrumbs are intentionally tiny and written *before* expensive phases so the
last durable marker survives a hard Render OOM kill. They are operational
telemetry only and never affect scoring, trading, or report decisions.
"""
from __future__ import annotations

from collections.abc import Callable
from datetime import datetime, timezone
from functools import wraps
from typing import Any, Literal, Mapping, ParamSpec, TypeVar
import os

LATEST_KEY = "runtime/oom_breadcrumb_latest.json"
EVENTS_KEY = "runtime/oom_breadcrumb_events.jsonl"
_Params = ParamSpec("_Params")
_Result = TypeVar("_Result")


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


def read_breadcrumb_history(
    limit: int = 500, *, source: Literal["active", "rolling", "legacy"] = "active"
) -> list[dict[str, Any]]:
    """Read diagnostics in persistence order.

    The active source follows the rollout flag. Select rolling or legacy to
    read that history regardless of the writer flag, including after rollback.
    """
    from services.storage_service import _env_bool, get_storage_service

    if source == "active":
        source = "rolling" if _env_bool("STORAGE_SHARED_REFERENCES_ENABLED", False) else "legacy"
    storage = get_storage_service()
    limit = max(0, int(limit))
    if source == "rolling":
        from services.oom_breadcrumb_budget import read_history

        return read_history(storage, limit)
    if source == "legacy":
        return storage.read_jsonl(EVENTS_KEY, limit=limit) if limit else []
    raise ValueError(f"Unknown OOM history source: {source!r}")


def with_breadcrumb_history_budget(run: Callable[_Params, _Result]) -> Callable[_Params, _Result]:
    """Give each report invocation a fresh history budget."""

    @wraps(run)
    def scoped(*args: _Params.args, **kwargs: _Params.kwargs) -> _Result:
        from services.storage_service import _env_bool

        if _env_bool("STORAGE_SHARED_REFERENCES_ENABLED", False):
            from services.oom_breadcrumb_budget import report_budget_scope

            with report_budget_scope():
                return run(*args, **kwargs)
        return run(*args, **kwargs)

    return scoped


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
        from services.storage_service import _env_bool, get_storage_service

        bounded_history = _env_bool("STORAGE_SHARED_REFERENCES_ENABLED", False)
        history = None
        if bounded_history:
            try:
                from services.oom_breadcrumb_budget import reserve_history

                history, payload["history_omitted"] = reserve_history(payload)
            except Exception:
                pass
        storage = get_storage_service()
        storage.write_json(LATEST_KEY, payload)
        try:
            if not bounded_history:
                storage.append_jsonl(EVENTS_KEY, payload)
            elif history is not None:
                from services.oom_breadcrumb_budget import append_history

                append_history(storage, history, payload["at"])
        except Exception:
            pass
        payload["persisted"] = True
    except Exception as exc:
        payload["persisted"] = False
        payload["persistence_error"] = f"{type(exc).__name__}: {str(exc)[:240]}"
    # stdout is useful even if PostgreSQL is transiently unavailable.
    try:
        mem = payload.get("memory") if isinstance(payload.get("memory"), Mapping) else {}
        history_status = f" history_omitted={payload['history_omitted']}" if "history_omitted" in payload else ""
        print(f"OOM_BREADCRUMB stage={payload['stage']} rss_mb={mem.get('process_rss_mb')} cgroup_mb={mem.get('cgroup_memory_current_mb')} persisted={payload.get('persisted')}{history_status}", flush=True)
    except Exception:
        pass
    return payload
