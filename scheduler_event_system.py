from __future__ import annotations

import json
import logging
import threading
import time
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from storage_architecture import runtime_data_path, runtime_log_path

LOG = logging.getLogger("app.scheduler")


def _now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


@dataclass(frozen=True)
class DomainEvent:
    event_id: str
    name: str
    payload: Dict[str, Any]
    source: str = "app"
    severity: str = "INFO"
    correlation_id: str = ""
    created_at: str = field(default_factory=_now_iso)


class DurableEventStore:
    """Append-only runtime event journal.

    The journal is runtime data and intentionally lives outside Git. A bounded
    snapshot is exposed to the UI while the file remains append-only for audit.
    """

    def __init__(self, path: Optional[Path] = None, max_read: int = 1000) -> None:
        self.path = path or runtime_log_path("events_v18682.jsonl")
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.max_read = max(50, int(max_read))
        self._lock = threading.RLock()

    def append(self, event: DomainEvent) -> None:
        row = json.dumps(asdict(event), ensure_ascii=False, default=str)
        with self._lock:
            with self.path.open("a", encoding="utf-8") as fh:
                fh.write(row + "\n")

    def recent(self, limit: int = 100) -> List[Dict[str, Any]]:
        limit = max(1, min(int(limit), self.max_read))
        if not self.path.exists():
            return []
        with self._lock:
            try:
                lines = self.path.read_text(encoding="utf-8").splitlines()[-limit:]
            except Exception:
                return []
        out: List[Dict[str, Any]] = []
        for line in lines:
            try:
                out.append(json.loads(line))
            except Exception:
                continue
        return out


class DomainEventBus:
    def __init__(self, store: Optional[DurableEventStore] = None) -> None:
        self.store = store or DurableEventStore()
        self._handlers: Dict[str, List[Callable[[DomainEvent], None]]] = {}
        self._lock = threading.RLock()
        self._recent: List[DomainEvent] = []

    def subscribe(self, event_name: str, handler: Callable[[DomainEvent], None]) -> None:
        with self._lock:
            handlers = self._handlers.setdefault(str(event_name), [])
            if handler not in handlers:
                handlers.append(handler)

    def unsubscribe(self, event_name: str, handler: Callable[[DomainEvent], None]) -> None:
        with self._lock:
            handlers = self._handlers.get(str(event_name), [])
            if handler in handlers:
                handlers.remove(handler)

    def publish(
        self,
        event_name: str,
        *,
        source: str = "app",
        severity: str = "INFO",
        correlation_id: str = "",
        **payload: Any,
    ) -> DomainEvent:
        event = DomainEvent(
            event_id=str(uuid.uuid4()),
            name=str(event_name),
            payload=dict(payload),
            source=str(source or "app"),
            severity=str(severity or "INFO").upper(),
            correlation_id=str(correlation_id or ""),
        )
        try:
            self.store.append(event)
        except Exception:
            LOG.exception("Could not persist event %s", event_name)
        with self._lock:
            self._recent.append(event)
            if len(self._recent) > 500:
                del self._recent[:-500]
            handlers = list(self._handlers.get(event.name, [])) + list(self._handlers.get("*", []))
        for handler in handlers:
            try:
                handler(event)
            except Exception:
                LOG.exception("Event handler failed: %s", event.name)
        return event

    def recent(self, limit: int = 50, include_persisted: bool = False) -> List[DomainEvent]:
        with self._lock:
            memory_rows = list(self._recent[-max(1, int(limit)):])
        if memory_rows or not include_persisted:
            return memory_rows
        rows = self.store.recent(limit)
        return [DomainEvent(**row) for row in rows if isinstance(row, dict)]


@dataclass
class JobState:
    name: str
    interval_seconds: int
    enabled: bool = True
    running: bool = False
    run_count: int = 0
    success_count: int = 0
    failure_count: int = 0
    skipped_count: int = 0
    consecutive_failures: int = 0
    last_started_at: Optional[str] = None
    last_finished_at: Optional[str] = None
    last_status: str = "NEVER"
    last_error: str = ""
    last_duration_ms: float = 0.0
    next_due_at: Optional[str] = None


class SchedulerCoordinator:
    """Single registry and guarded execution layer for all background work.

    It does not start hidden threads. Existing cron/Render invocations call
    ``run_job`` so all jobs get the same lock, metrics, event trail and errors.
    """

    def __init__(self, event_bus: DomainEventBus, state_path: Optional[Path] = None) -> None:
        self.event_bus = event_bus
        self.state_path = state_path or runtime_data_path("scheduler_state_v18682.json")
        self.state_path.parent.mkdir(parents=True, exist_ok=True)
        self._jobs: Dict[str, JobState] = {}
        self._job_locks: Dict[str, threading.Lock] = {}
        self._lock = threading.RLock()
        self._load()

    def _load(self) -> None:
        if not self.state_path.exists():
            return
        try:
            raw = json.loads(self.state_path.read_text(encoding="utf-8"))
            for row in raw.get("jobs", []):
                state = JobState(**row)
                state.running = False
                self._jobs[state.name] = state
        except Exception:
            LOG.exception("Could not load scheduler state")

    def _save(self) -> None:
        payload = {"updated_at": _now_iso(), "jobs": [asdict(v) for v in self._jobs.values()]}
        tmp = self.state_path.with_suffix(".tmp")
        tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        tmp.replace(self.state_path)

    def register(self, name: str, interval_seconds: int, enabled: bool = True) -> JobState:
        name = str(name)
        with self._lock:
            state = self._jobs.get(name) or JobState(name=name, interval_seconds=max(1, int(interval_seconds)))
            state.interval_seconds = max(1, int(interval_seconds))
            state.enabled = bool(enabled)
            self._jobs[name] = state
            self._job_locks.setdefault(name, threading.Lock())
            self._save()
            return state

    def set_enabled(self, name: str, enabled: bool) -> None:
        with self._lock:
            state = self._jobs[name]
            state.enabled = bool(enabled)
            self._save()
        self.event_bus.publish("scheduler.job.enabled_changed", source="scheduler", job=name, enabled=enabled)

    def run_job(
        self,
        name: str,
        func: Callable[..., Any],
        *args: Any,
        force: bool = False,
        **kwargs: Any,
    ) -> Any:
        with self._lock:
            if name not in self._jobs:
                self.register(name, 60)
            state = self._jobs[name]
            lock = self._job_locks.setdefault(name, threading.Lock())
            if not state.enabled and not force:
                state.skipped_count += 1
                state.last_status = "DISABLED"
                self._save()
                self.event_bus.publish("scheduler.job.skipped", source="scheduler", job=name, reason="disabled")
                return None
        if not lock.acquire(blocking=False):
            with self._lock:
                state.skipped_count += 1
                state.last_status = "SKIPPED_RUNNING"
                self._save()
            self.event_bus.publish("scheduler.job.skipped", source="scheduler", job=name, reason="already_running")
            return None

        started = time.perf_counter()
        correlation_id = str(uuid.uuid4())
        with self._lock:
            state.running = True
            state.run_count += 1
            state.last_started_at = _now_iso()
            state.last_status = "RUNNING"
            state.last_error = ""
            self._save()
        self.event_bus.publish("scheduler.job.started", source="scheduler", correlation_id=correlation_id, job=name)
        try:
            result = func(*args, **kwargs)
            duration = (time.perf_counter() - started) * 1000.0
            with self._lock:
                state.success_count += 1
                state.consecutive_failures = 0
                state.last_status = "OK"
                state.last_duration_ms = round(duration, 2)
                state.last_finished_at = _now_iso()
                state.running = False
                self._save()
            self.event_bus.publish(
                "scheduler.job.completed", source="scheduler", correlation_id=correlation_id,
                job=name, duration_ms=round(duration, 2)
            )
            return result
        except Exception as exc:
            duration = (time.perf_counter() - started) * 1000.0
            with self._lock:
                state.failure_count += 1
                state.consecutive_failures += 1
                state.last_status = "ERROR"
                state.last_error = f"{type(exc).__name__}: {exc}"
                state.last_duration_ms = round(duration, 2)
                state.last_finished_at = _now_iso()
                state.running = False
                self._save()
            self.event_bus.publish(
                "scheduler.job.failed", source="scheduler", severity="ERROR", correlation_id=correlation_id,
                job=name, duration_ms=round(duration, 2), error=state.last_error
            )
            raise
        finally:
            lock.release()

    def mark_run(self, name: str, status: str = "OK", duration_ms: float = 0.0) -> None:
        """Compatibility hook for legacy workers that already manage execution."""
        with self._lock:
            if name not in self._jobs:
                self.register(name, 60)
            state = self._jobs[name]
            state.run_count += 1
            state.last_started_at = state.last_started_at or _now_iso()
            state.last_finished_at = _now_iso()
            state.last_status = str(status or "OK").upper()
            state.last_duration_ms = round(float(duration_ms or 0.0), 2)
            state.running = False
            if state.last_status == "OK":
                state.success_count += 1
                state.consecutive_failures = 0
            elif state.last_status == "ERROR":
                state.failure_count += 1
                state.consecutive_failures += 1
            self._save()

    def snapshot(self) -> List[Dict[str, Any]]:
        with self._lock:
            return [asdict(self._jobs[name]) for name in sorted(self._jobs)]

    def health(self) -> Dict[str, Any]:
        rows = self.snapshot()
        status = "GREEN"
        if any(row["last_status"] == "ERROR" or row["consecutive_failures"] >= 3 for row in rows):
            status = "RED"
        elif any(row["last_status"] in {"NEVER", "DISABLED", "SKIPPED_RUNNING"} for row in rows):
            status = "YELLOW"
        return {"status": status, "jobs": rows, "state_path": str(self.state_path)}


_EVENT_STORE = DurableEventStore()
_EVENT_BUS = DomainEventBus(_EVENT_STORE)
_SCHEDULER = SchedulerCoordinator(_EVENT_BUS)


def get_domain_event_bus() -> DomainEventBus:
    return _EVENT_BUS


def get_scheduler() -> SchedulerCoordinator:
    return _SCHEDULER
