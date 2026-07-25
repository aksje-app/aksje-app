"""Structured operational telemetry for AI Aksje Analyzer v19.1.0.

This module is observational only. It records structured events, stable error
codes, source health and end-to-end run traces. It must never alter ranking,
trading, portfolio or autonomy decisions.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from statistics import median
from threading import RLock
from typing import Any, Mapping, Sequence
import hashlib
import os
import re
import time
import uuid

from durable_runtime import append_event, read_events, read_json, write_json
from runtime_env import redact_secrets
from storage_architecture import runtime_data_path, runtime_log_path

COMPONENT_VERSION = "v19.2.0"
EVENTS_PATH = runtime_log_path("operations", "events.jsonl")
ERRORS_PATH = runtime_log_path("operations", "errors.jsonl")
SOURCE_EVENTS_PATH = runtime_log_path("operations", "source_health.jsonl")
TRACE_EVENTS_PATH = runtime_log_path("operations", "run_traces.jsonl")
SOURCE_STATE_PATH = runtime_data_path("operations", "source_health_state.json")
TRACE_INDEX_PATH = runtime_data_path("operations", "run_trace_index.json")
TRACE_DIR = runtime_data_path("operations", "run_traces")
_LOCK = RLock()
FAILURE_ALERT_THRESHOLD = max(1, int(os.getenv("SOURCE_HEALTH_FAILURE_ALERT_THRESHOLD", "3") or 3))
FALLBACK_ALERT_THRESHOLD = max(1, int(os.getenv("SOURCE_HEALTH_FALLBACK_ALERT_THRESHOLD", "3") or 3))
VOLUME_LOW_RATIO = max(0.0, float(os.getenv("SOURCE_HEALTH_VOLUME_LOW_RATIO", "0.20") or 0.20))
VOLUME_HIGH_RATIO = max(1.0, float(os.getenv("SOURCE_HEALTH_VOLUME_HIGH_RATIO", "5.0") or 5.0))

ERROR_CODE_SUFFIXES = {
    "fetch_failed": "0042",
    "parse_failed": "0043",
    "volume_anomaly": "0044",
    "stale_fallback": "0045",
    "scheduler_failed": "0001",
    "coordination_degraded": "0002",
    "runtime_worker_failed": "0001",
    "delivery_repair_failed": "0002",
    "report_run_failed": "0001",
    "report_stage_failed": "0002",
    "storage_failed": "0001",
    "unexpected": "9999",
}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _slug(value: Any, default: str = "GENERAL") -> str:
    text = re.sub(r"[^A-Z0-9]+", "-", str(value or "").upper()).strip("-")
    return (text or default)[:32]


def stable_error_code(component: str, category: str, subject: str = "") -> str:
    """Return a stable, human-searchable error code.

    Example: stable_error_code("NEWS", "fetch_failed", "EFN") -> NEWS-EFN-0042.
    """
    suffix = ERROR_CODE_SUFFIXES.get(str(category or "").casefold(), ERROR_CODE_SUFFIXES["unexpected"])
    component_slug = _slug(component)
    subject_slug = _slug(subject, "GENERAL")
    return f"{component_slug}-{subject_slug}-{suffix}"


def _safe_error(value: Any, limit: int = 1200) -> str:
    return redact_secrets(value).strip()[:limit]


def _safe_details(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {str(key): _safe_details(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_safe_details(item) for item in value]
    if isinstance(value, str):
        return redact_secrets(value)[:1500]
    return value


def _safe_append(key: str, path: Path, row: Mapping[str, Any]) -> bool:
    """Write once through durable_runtime -> repository, with local mirror."""
    try:
        append_event(key, path, row)
        return True
    except Exception:
        return False


def _safe_read_events(key: str, path: Path, limit: int) -> list[dict[str, Any]]:
    try:
        return list(read_events(key, path, limit=limit) or [])
    except Exception:
        return []


def _safe_read_json(key: str, path: Path, default: Any) -> Any:
    try:
        return read_json(key, path, default)
    except Exception:
        return default


def _safe_write_json(key: str, path: Path, value: Any) -> bool:
    try:
        write_json(key, path, value)
        return True
    except Exception:
        return False

def _event_id(payload: Mapping[str, Any]) -> str:
    seed = "|".join(str(payload.get(key) or "") for key in ("at", "event", "component", "run_id", "source_id", "message"))
    return "EVT-" + hashlib.sha1(seed.encode("utf-8")).hexdigest()[:16].upper()


def record_event(
    event: str,
    *,
    severity: str = "INFO",
    component: str = "SYSTEM",
    stage: str = "",
    message: str = "",
    run_id: str = "",
    report_id: str = "",
    job_id: str = "",
    source_id: str = "",
    error_code: str = "",
    error: Any = "",
    fallback_used: bool = False,
    details: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    row = {
        "at": _now(),
        "event": _slug(event, "EVENT"),
        "severity": _slug(severity, "INFO"),
        "component": _slug(component, "SYSTEM"),
        "stage": _slug(stage, "") if stage else "",
        "message": str(message or "")[:1000],
        "run_id": str(run_id or ""),
        "report_id": str(report_id or ""),
        "job_id": str(job_id or ""),
        "source_id": str(source_id or ""),
        "error_code": str(error_code or ""),
        "error": _safe_error(error),
        "fallback_used": bool(fallback_used),
        "details": _safe_details(dict(details or {})),
    }
    row["event_id"] = _event_id(row)
    _safe_append("operations/events.jsonl", EVENTS_PATH, row)
    if row["severity"] in {"ERROR", "CRITICAL"} or row["error_code"]:
        _safe_append("operations/errors.jsonl", ERRORS_PATH, row)
    return row


def list_operational_events(limit: int = 500, *, severity: str = "", run_id: str = "") -> list[dict[str, Any]]:
    rows = _safe_read_events("operations/events.jsonl", EVENTS_PATH, limit=max(limit * 3, limit))
    if severity:
        wanted = _slug(severity)
        rows = [row for row in rows if str(row.get("severity") or "") == wanted]
    if run_id:
        rows = [row for row in rows if str(row.get("run_id") or "") == str(run_id)]
    return rows[-limit:]


def list_operational_errors(limit: int = 200) -> list[dict[str, Any]]:
    return _safe_read_events("operations/errors.jsonl", ERRORS_PATH, limit=limit)


@dataclass
class RunTrace:
    trace_id: str
    run_id: str
    report_id: str
    kind: str
    trigger: str
    job_id: str
    status: str
    started_at: str
    completed_at: str = ""
    duration_seconds: float | None = None
    current_stage: str = "START"
    stages: list[dict[str, Any]] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)
    error_code: str = ""
    error: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def new_trace_id(prefix: str = "RUN") -> str:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    return f"{_slug(prefix)}-{stamp}-{uuid.uuid4().hex[:8].upper()}"


def _trace_path(trace_id: str) -> Path:
    return TRACE_DIR / f"{_slug(trace_id, 'TRACE')}.json"


def _load_trace_index() -> list[dict[str, Any]]:
    value = _safe_read_json("operations/run_trace_index.json", TRACE_INDEX_PATH, [])
    return list(value or []) if isinstance(value, list) else []


def _save_trace(trace: Mapping[str, Any]) -> None:
    trace_id = str(trace.get("trace_id") or "")
    if not trace_id:
        return
    _safe_write_json(f"operations/run_traces/{trace_id}.json", _trace_path(trace_id), dict(trace))
    index = [row for row in _load_trace_index() if str(row.get("trace_id") or "") != trace_id]
    summary = {key: trace.get(key) for key in (
        "trace_id", "run_id", "report_id", "kind", "trigger", "job_id", "status",
        "started_at", "completed_at", "duration_seconds", "current_stage", "error_code", "error",
    )}
    index.insert(0, summary)
    _safe_write_json("operations/run_trace_index.json", TRACE_INDEX_PATH, index[:1000])


def begin_run_trace(
    *,
    trace_id: str | None = None,
    run_id: str = "",
    report_id: str = "",
    kind: str = "REPORT",
    trigger: str = "",
    job_id: str = "",
    metadata: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    trace = RunTrace(
        trace_id=trace_id or new_trace_id(kind),
        run_id=str(run_id or ""),
        report_id=str(report_id or ""),
        kind=_slug(kind),
        trigger=str(trigger or ""),
        job_id=str(job_id or ""),
        status="RUNNING",
        started_at=_now(),
        metadata=dict(metadata or {}),
    ).to_dict()
    with _LOCK:
        _save_trace(trace)
    record_event("RUN_STARTED", component=kind, stage="START", message="Kjøringen startet", run_id=run_id,
                 report_id=report_id, job_id=job_id, details={"trace_id": trace["trace_id"], **dict(metadata or {})})
    return trace


def load_run_trace(trace_id: str) -> dict[str, Any]:
    value = _safe_read_json(f"operations/run_traces/{trace_id}.json", _trace_path(trace_id), {})
    return dict(value or {}) if isinstance(value, Mapping) else {}


def bind_run_trace(trace_id: str, *, run_id: str = "", report_id: str = "", job_id: str = "") -> dict[str, Any]:
    with _LOCK:
        trace = load_run_trace(trace_id)
        if not trace:
            return {}
        if run_id:
            trace["run_id"] = str(run_id)
        if report_id:
            trace["report_id"] = str(report_id)
        if job_id:
            trace["job_id"] = str(job_id)
        _save_trace(trace)
        return trace


def mark_run_stage(
    trace_id: str,
    stage: str,
    *,
    status: str = "COMPLETED",
    message: str = "",
    metrics: Mapping[str, Any] | None = None,
    error_code: str = "",
    error: Any = "",
) -> dict[str, Any]:
    with _LOCK:
        trace = load_run_trace(trace_id)
        if not trace:
            return {}
        stage_row = {
            "at": _now(),
            "stage": _slug(stage, "UNKNOWN"),
            "status": _slug(status, "COMPLETED"),
            "message": str(message or "")[:1000],
            "metrics": dict(metrics or {}),
            "error_code": str(error_code or ""),
            "error": _safe_error(error),
        }
        trace.setdefault("stages", []).append(stage_row)
        trace["current_stage"] = stage_row["stage"]
        if stage_row["status"] in {"FAILED", "ERROR"}:
            trace["status"] = "DEGRADED"
            trace["error_code"] = stage_row["error_code"]
            trace["error"] = stage_row["error"]
        _save_trace(trace)
    severity = "ERROR" if stage_row["status"] in {"FAILED", "ERROR"} else "INFO"
    record_event(
        "RUN_STAGE", severity=severity, component=str(trace.get("kind") or "RUN"), stage=stage_row["stage"],
        message=stage_row["message"], run_id=str(trace.get("run_id") or ""), report_id=str(trace.get("report_id") or ""),
        job_id=str(trace.get("job_id") or ""), error_code=stage_row["error_code"], error=stage_row["error"],
        details={"trace_id": trace_id, "status": stage_row["status"], **stage_row["metrics"]},
    )
    return trace


def complete_run_trace(
    trace_id: str,
    *,
    status: str = "COMPLETED",
    error_code: str = "",
    error: Any = "",
    metrics: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    with _LOCK:
        trace = load_run_trace(trace_id)
        if not trace:
            return {}
        completed = _now()
        try:
            started = datetime.fromisoformat(str(trace.get("started_at") or "").replace("Z", "+00:00"))
            duration = max(0.0, (datetime.fromisoformat(completed) - started).total_seconds())
        except Exception:
            duration = None
        trace.update({
            "status": _slug(status, "COMPLETED"),
            "completed_at": completed,
            "duration_seconds": round(duration, 3) if duration is not None else None,
            "current_stage": "COMPLETE" if _slug(status) == "COMPLETED" else "FAILED",
            "error_code": str(error_code or trace.get("error_code") or ""),
            "error": _safe_error(error or trace.get("error") or ""),
        })
        if metrics:
            trace.setdefault("metadata", {}).update(dict(metrics))
        _save_trace(trace)
    severity = "INFO" if trace["status"] == "COMPLETED" else "ERROR"
    record_event(
        "RUN_COMPLETED" if severity == "INFO" else "RUN_FAILED", severity=severity,
        component=str(trace.get("kind") or "RUN"), stage=trace["current_stage"],
        message="Kjøringen er fullført" if severity == "INFO" else "Kjøringen feilet",
        run_id=str(trace.get("run_id") or ""), report_id=str(trace.get("report_id") or ""),
        job_id=str(trace.get("job_id") or ""), error_code=trace["error_code"], error=trace["error"],
        details={"trace_id": trace_id, "duration_seconds": trace.get("duration_seconds")},
    )
    _safe_append("operations/run_traces.jsonl", TRACE_EVENTS_PATH, trace)
    return trace


def list_run_traces(limit: int = 100) -> list[dict[str, Any]]:
    return _load_trace_index()[:max(0, int(limit))]


def _load_source_state() -> dict[str, Any]:
    value = _safe_read_json("operations/source_health_state.json", SOURCE_STATE_PATH, {})
    return dict(value or {}) if isinstance(value, Mapping) else {}


def _source_score(state: Mapping[str, Any]) -> int:
    score = 100.0
    failures = int(state.get("consecutive_failures") or 0)
    score -= min(60, failures * 20)
    response_ms = float(state.get("last_response_ms") or 0.0)
    if response_ms > 8000:
        score -= 20
    elif response_ms > 4000:
        score -= 10
    elif response_ms > 2000:
        score -= 5
    if state.get("fallback_used"):
        score -= min(24, 8 + int(state.get("consecutive_fallbacks") or 0) * 4)
    if str(state.get("parser_status") or "OK") != "OK":
        score -= 25
    if state.get("volume_anomaly"):
        score -= 15
    if not state.get("last_success_at"):
        score -= 20
    return int(max(0, min(100, round(score))))


def record_source_attempt(
    *,
    source_id: str,
    market: str = "",
    publisher: str = "",
    url: str = "",
    success: bool,
    response_ms: float | None = None,
    article_count: int = 0,
    relevant_count: int = 0,
    duplicate_count: int = 0,
    filtered_commercial_count: int = 0,
    fallback_used: bool = False,
    cache_status: str = "",
    parser_status: str = "OK",
    error: Any = "",
    volume_check: bool = True,
) -> dict[str, Any]:
    source_id = str(source_id or "unknown")
    now = _now()
    with _LOCK:
        state_all = _load_source_state()
        previous = dict(state_all.get(source_id) or {})
        history = list(previous.get("volume_history") or [])[-29:]
        if success:
            history.append({"at": now, "article_count": int(article_count), "relevant_count": int(relevant_count)})
        baseline_values = [int(row.get("article_count") or 0) for row in history[:-1] if int(row.get("article_count") or 0) > 0]
        baseline = float(median(baseline_values[-14:])) if baseline_values else 0.0
        volume_ratio = (float(article_count) / baseline) if baseline > 0 else None
        volume_anomaly = bool(
            success and volume_check and baseline >= 5 and volume_ratio is not None
            and (volume_ratio < VOLUME_LOW_RATIO or volume_ratio > VOLUME_HIGH_RATIO)
        )
        consecutive = 0 if success else int(previous.get("consecutive_failures") or 0) + 1
        fallback_streak = (int(previous.get("consecutive_fallbacks") or 0) + 1) if success and fallback_used else 0
        state = {
            "source_id": source_id,
            "market": str(market or previous.get("market") or ""),
            "publisher": str(publisher or previous.get("publisher") or source_id),
            "url": str(url or previous.get("url") or ""),
            "last_attempt_at": now,
            "last_success_at": now if success else str(previous.get("last_success_at") or ""),
            "last_failure_at": "" if success else now,
            "last_new_article_at": now if success and article_count > 0 else str(previous.get("last_new_article_at") or ""),
            "last_response_ms": round(float(response_ms or 0.0), 1),
            "consecutive_failures": consecutive,
            "consecutive_fallbacks": fallback_streak,
            "last_error": "" if success else _safe_error(error, 500),
            "error_code": "" if success else stable_error_code(
                "NEWS", "parse_failed" if str(parser_status or "").upper() == "FAILED" else "fetch_failed", source_id
            ),
            "fallback_used": bool(fallback_used),
            "cache_status": str(cache_status or ""),
            "parser_status": str(parser_status or "OK"),
            "article_count": int(article_count),
            "relevant_count": int(relevant_count),
            "duplicate_count": int(duplicate_count),
            "filtered_commercial_count": int(filtered_commercial_count),
            "volume_baseline": round(baseline, 2),
            "volume_ratio": round(volume_ratio, 3) if volume_ratio is not None else None,
            "volume_anomaly": volume_anomaly,
            "alert": bool(consecutive >= FAILURE_ALERT_THRESHOLD or fallback_streak >= FALLBACK_ALERT_THRESHOLD or volume_anomaly or str(parser_status or "OK") != "OK"),
            "volume_history": history,
        }
        state["health_score"] = _source_score(state)
        state_all[source_id] = state
        _safe_write_json("operations/source_health_state.json", SOURCE_STATE_PATH, state_all)
    error_code = state.get("error_code") or (stable_error_code("NEWS", "volume_anomaly", source_id) if volume_anomaly else "")
    event = {
        **{key: state.get(key) for key in state if key != "volume_history"},
        "success": bool(success),
    }
    _safe_append("operations/source_health.jsonl", SOURCE_EVENTS_PATH, event)
    record_event(
        "SOURCE_FETCH_OK" if success else "SOURCE_FETCH_FAILED",
        severity="WARNING" if (not success or state["alert"]) else "INFO",
        component="NEWS", stage="SOURCE_FETCH", message=("Kilden ble hentet" if success else "Kildehenting feilet"),
        source_id=source_id, error_code=str(error_code or ""), error=error, fallback_used=fallback_used,
        details={key: event.get(key) for key in (
            "market", "publisher", "last_response_ms", "article_count", "relevant_count", "duplicate_count",
            "filtered_commercial_count", "cache_status", "parser_status", "consecutive_failures", "consecutive_fallbacks", "health_score",
            "volume_baseline", "volume_ratio", "volume_anomaly", "alert",
        )},
    )
    return state


def source_health_snapshot(registry: Mapping[str, Sequence[Mapping[str, Any]]] | None = None) -> list[dict[str, Any]]:
    state = _load_source_state()
    rows: list[dict[str, Any]] = []
    seen: set[str] = set()
    if registry:
        for market, specs in registry.items():
            for spec in specs:
                source_id = str(spec.get("id") or "")
                current = dict(state.get(source_id) or {})
                current.update({
                    "source_id": source_id,
                    "id": source_id,
                    "market": str(current.get("market") or market),
                    "publisher": str(current.get("publisher") or spec.get("publisher") or spec.get("label") or source_id),
                    "label": str(spec.get("label") or spec.get("publisher") or source_id),
                    "url": str(current.get("url") or spec.get("url") or ""),
                    "source_role": str(spec.get("source_role") or ""),
                })
                if "health_score" not in current:
                    current["health_score"] = _source_score(current)
                rows.append(current)
                seen.add(source_id)
    for source_id, value in state.items():
        if source_id in seen:
            continue
        current = dict(value or {})
        current.setdefault("source_id", source_id)
        current.setdefault("id", source_id)
        rows.append(current)
    return sorted(rows, key=lambda row: (str(row.get("market") or ""), str(row.get("publisher") or "")))


def source_health_events(limit: int = 500) -> list[dict[str, Any]]:
    return _safe_read_events("operations/source_health.jsonl", SOURCE_EVENTS_PATH, limit=limit)


__all__ = [
    "COMPONENT_VERSION", "stable_error_code", "record_event", "list_operational_events",
    "list_operational_errors", "new_trace_id", "begin_run_trace", "bind_run_trace",
    "mark_run_stage", "complete_run_trace", "load_run_trace", "list_run_traces",
    "record_source_attempt", "source_health_snapshot", "source_health_events",
]
