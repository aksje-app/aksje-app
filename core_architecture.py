from __future__ import annotations

import json
import logging
import os
import platform
import queue
import sys
import threading
import time
from dataclasses import dataclass, field, asdict
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Dict, Iterable, List, Optional

from storage_architecture import runtime_data_path, runtime_log_path
from scheduler_event_system import get_domain_event_bus, get_scheduler


@dataclass
class NavigationState:
    main_area: str = ""
    group: str = ""
    panel: str = ""
    tab: str = ""
    subtab: str = ""


@dataclass
class PaperTradingState:
    active_symbol: str = ""
    manual_override: str = "OFF"
    selected_tab: str = "Handel"


@dataclass
class PortfolioState:
    selected_symbol: str = ""
    selected_asset_type: str = "Aksje"


@dataclass
class DiscoveryState:
    selected_tab: str = "Discovery Dashboard"
    selected_signal: str = ""


@dataclass
class NotificationState:
    pushover_enabled: bool = True
    last_event: str = ""


@dataclass
class RuntimeState:
    last_error: str = ""
    last_action: str = ""


@dataclass
class LearningState:
    collect_data: bool = True
    analyze: bool = True
    recommendations: bool = True
    auto_optimize: bool = False
    auto_rule_changes: bool = False


@dataclass
class AppState:
    navigation: NavigationState = field(default_factory=NavigationState)
    paper_trading: PaperTradingState = field(default_factory=PaperTradingState)
    portfolio: PortfolioState = field(default_factory=PortfolioState)
    discovery: DiscoveryState = field(default_factory=DiscoveryState)
    notifications: NotificationState = field(default_factory=NotificationState)
    runtime: RuntimeState = field(default_factory=RuntimeState)
    learning: LearningState = field(default_factory=LearningState)
    updated_at: str = field(default_factory=lambda: datetime.now().isoformat(timespec="seconds"))

    def to_dict(self) -> Dict[str, Any]:
        self.updated_at = datetime.now().isoformat(timespec="seconds")
        return asdict(self)


class AppStateStore:
    """Small typed facade over Streamlit session state.

    The existing keys remain compatible; this model provides a single stable
    namespace for new code and gradual migration.
    """

    KEY = "app_state_v18680"

    @classmethod
    def load(cls, session_state: Any) -> AppState:
        raw = session_state.get(cls.KEY)
        if isinstance(raw, AppState):
            return raw
        if not isinstance(raw, dict):
            state = AppState()
            session_state[cls.KEY] = state
            return state
        try:
            state = AppState(
                navigation=NavigationState(**(raw.get("navigation") or {})),
                paper_trading=PaperTradingState(**(raw.get("paper_trading") or {})),
                portfolio=PortfolioState(**(raw.get("portfolio") or {})),
                discovery=DiscoveryState(**(raw.get("discovery") or {})),
                notifications=NotificationState(**(raw.get("notifications") or {})),
                runtime=RuntimeState(**(raw.get("runtime") or {})),
                learning=LearningState(**(raw.get("learning") or {})),
                updated_at=str(raw.get("updated_at") or ""),
            )
        except Exception:
            state = AppState()
        session_state[cls.KEY] = state
        return state

    @classmethod
    def save(cls, session_state: Any, state: AppState) -> None:
        session_state[cls.KEY] = state


@dataclass(frozen=True)
class Event:
    name: str
    payload: Dict[str, Any]
    created_at: str = field(default_factory=lambda: datetime.now().isoformat(timespec="seconds"))


class EventBus:
    def __init__(self) -> None:
        self._handlers: Dict[str, List[Callable[[Event], None]]] = {}
        self._lock = threading.RLock()
        self._recent: List[Event] = []

    def subscribe(self, event_name: str, handler: Callable[[Event], None]) -> None:
        with self._lock:
            self._handlers.setdefault(event_name, []).append(handler)

    def publish(self, event_name: str, **payload: Any) -> Event:
        event = Event(event_name, dict(payload))
        with self._lock:
            self._recent.append(event)
            if len(self._recent) > 200:
                del self._recent[:-200]
            handlers = list(self._handlers.get(event_name, [])) + list(self._handlers.get("*", []))
        for handler in handlers:
            try:
                handler(event)
            except Exception:
                logging.getLogger("app.event_bus").exception("Event handler failed: %s", event_name)
        return event

    def recent(self, limit: int = 50) -> List[Event]:
        with self._lock:
            return list(self._recent[-max(1, limit):])


class ServiceContainer:
    def __init__(self) -> None:
        self._services: Dict[str, Any] = {}
        self._factories: Dict[str, Callable[["ServiceContainer"], Any]] = {}
        self._lock = threading.RLock()

    def register(self, name: str, service: Any) -> None:
        with self._lock:
            self._services[name] = service

    def register_factory(self, name: str, factory: Callable[["ServiceContainer"], Any]) -> None:
        with self._lock:
            self._factories[name] = factory

    def get(self, name: str) -> Any:
        with self._lock:
            if name not in self._services and name in self._factories:
                self._services[name] = self._factories[name](self)
            if name not in self._services:
                raise KeyError(f"Unknown service: {name}")
            return self._services[name]

    def names(self) -> List[str]:
        with self._lock:
            return sorted(set(self._services) | set(self._factories))


@dataclass
class ScheduledJob:
    name: str
    interval_seconds: int
    enabled: bool = True
    last_run: Optional[str] = None
    last_status: str = "NEVER"
    last_duration_ms: float = 0.0


class SchedulerRegistry:
    """Registry/health layer for background jobs.

    Existing schedulers can register their status here without being rewritten.
    This avoids running a second competing scheduler.
    """

    def __init__(self) -> None:
        self._jobs: Dict[str, ScheduledJob] = {}
        self._lock = threading.RLock()

    def register(self, name: str, interval_seconds: int, enabled: bool = True) -> ScheduledJob:
        with self._lock:
            job = self._jobs.get(name) or ScheduledJob(name=name, interval_seconds=max(1, interval_seconds))
            job.interval_seconds = max(1, interval_seconds)
            job.enabled = bool(enabled)
            self._jobs[name] = job
            return job

    def mark_run(self, name: str, status: str = "OK", duration_ms: float = 0.0) -> None:
        with self._lock:
            job = self._jobs.setdefault(name, ScheduledJob(name=name, interval_seconds=60))
            job.last_run = datetime.now().isoformat(timespec="seconds")
            job.last_status = str(status or "OK")
            job.last_duration_ms = round(float(duration_ms or 0.0), 2)

    def snapshot(self) -> List[Dict[str, Any]]:
        with self._lock:
            return [asdict(job) for job in self._jobs.values()]


_EVENT_BUS = get_domain_event_bus()
_SERVICES = ServiceContainer()
_SCHEDULER = get_scheduler()
_INITIALIZED = False


def get_event_bus() -> Any:
    return _EVENT_BUS


def get_services() -> ServiceContainer:
    return _SERVICES


def get_scheduler_registry() -> Any:
    return _SCHEDULER


def configure_logging() -> Path:
    log_path = runtime_log_path("application.log")
    log_path.parent.mkdir(parents=True, exist_ok=True)
    root = logging.getLogger()
    root.setLevel(logging.INFO)
    existing = {getattr(handler, "baseFilename", None) for handler in root.handlers}
    if str(log_path) not in existing:
        handler = logging.FileHandler(log_path, encoding="utf-8")
        handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s %(message)s"))
        root.addHandler(handler)
    return log_path


def initialize_core_runtime() -> None:
    global _INITIALIZED
    if _INITIALIZED:
        return
    configure_logging()
    _SERVICES.register("event_bus", _EVENT_BUS)
    _SERVICES.register("scheduler", _SCHEDULER)
    _SERVICES.register("scheduler_registry", _SCHEDULER)
    from services.app_state_service import get_app_state_service
    from services.currency_service import get_currency_service
    from services.notification_service import get_notification_service
    from services.review_queue_service import get_review_queue_service
    from services.trading_rule_service import get_trading_rule_service
    _SERVICES.register("app_state", get_app_state_service())
    _SERVICES.register("currency", get_currency_service())
    _SERVICES.register("notifications", get_notification_service())
    _SERVICES.register("review_queue", get_review_queue_service())
    _SERVICES.register("trading_rules", get_trading_rule_service())
    _SCHEDULER.register("Background Market Scan", 900)
    _SCHEDULER.register("Currency Monitor", 300)
    _SCHEDULER.register("Market Update", 300)
    _SCHEDULER.register("AI Discovery", 900)
    _SCHEDULER.register("Learning Analytics", 3600)
    _SCHEDULER.register("Runtime Cleanup", 86400)
    _EVENT_BUS.publish("runtime.initialized", source="core_architecture", services=_SERVICES.names())
    _INITIALIZED = True


def _memory_snapshot() -> Dict[str, Any]:
    result: Dict[str, Any] = {"rss_mb": None, "cpu_percent": None}
    try:
        import psutil  # type: ignore
        proc = psutil.Process(os.getpid())
        result["rss_mb"] = round(proc.memory_info().rss / 1024 / 1024, 1)
        result["cpu_percent"] = proc.cpu_percent(interval=0.0)
    except Exception:
        pass
    return result


def system_health_snapshot() -> Dict[str, Any]:
    initialize_core_runtime()
    memory = _memory_snapshot()
    checks = []

    def add(name: str, ok: bool, detail: str, severity: str = "ERROR") -> None:
        checks.append({"component": name, "status": "GREEN" if ok else ("YELLOW" if severity == "WARN" else "RED"), "detail": detail})

    runtime_root = runtime_data_path().parent
    add("Runtime storage", runtime_root.exists(), str(runtime_root))
    add("Writable storage", os.access(runtime_root, os.W_OK), "Skrivbar" if os.access(runtime_root, os.W_OK) else "Ikke skrivbar")
    add("Database configuration", bool(os.getenv("DATABASE_URL")), "DATABASE_URL satt" if os.getenv("DATABASE_URL") else "Lokal fallback aktiv", "WARN")
    add("Python", True, platform.python_version())
    add("Event Bus", True, f"{len(_EVENT_BUS.recent(200))} nylige hendelser")
    add("Services", True, ", ".join(_SERVICES.names()) or "Ingen")
    scheduler_health = _SCHEDULER.health()
    add("Scheduler", scheduler_health.get("status") != "RED", f"{len(_SCHEDULER.snapshot())} registrerte jobber / {scheduler_health.get('status')}", "WARN")

    overall = "GREEN"
    if any(row["status"] == "RED" for row in checks):
        overall = "RED"
    elif any(row["status"] == "YELLOW" for row in checks):
        overall = "YELLOW"
    return {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "overall": overall,
        "checks": checks,
        "memory": memory,
        "python": sys.version.split()[0],
        "platform": platform.platform(),
        "scheduler": _SCHEDULER.snapshot(),
        "recent_events": [asdict(event) for event in _EVENT_BUS.recent(25, include_persisted=True)],
    }


def render_system_health_dashboard() -> None:
    import streamlit as st
    from performance_monitor import snapshot as performance_snapshot

    data = system_health_snapshot()
    perf = performance_snapshot()
    st.subheader("System Health")
    st.caption("Samlet helsesjekk for runtime, storage, tjenester, scheduler og ytelse. Ingen tradinglogikk endres her.")
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Status", data["overall"])
    c2.metric("RAM", f"{data['memory'].get('rss_mb')} MB" if data['memory'].get('rss_mb') is not None else "Ukjent")
    c3.metric("Reruns", perf.get("reruns", 0))
    slowest = (perf.get("panel_summary") or [{}])[0]
    c4.metric("Tregeste panel", slowest.get("Panel", "-"), f"{slowest.get('Snitt ms', 0)} ms" if slowest else None)
    st.dataframe(data["checks"], use_container_width=True, hide_index=True)
    with st.expander("Scheduler", expanded=False):
        st.dataframe(data["scheduler"], use_container_width=True, hide_index=True)
    with st.expander("Registrerte tjenester og hendelser", expanded=False):
        st.write({"services": get_services().names()})
        st.dataframe(data["recent_events"], use_container_width=True, hide_index=True)
