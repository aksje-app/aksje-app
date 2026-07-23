"""One-shot unattended scheduler entry point for Render Cron Jobs.

This process has no Streamlit or login dependency. It records a durable
heartbeat, repairs public reports independently, and then runs the coordinated
due-job check. A report-repair failure can never suppress a scheduled scan.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

from durable_runtime import read_json, write_json
from storage_architecture import runtime_data_path

STATE_KEY = "scheduler/unattended_state.json"
STATE_PATH = runtime_data_path("scheduler", "unattended_state.json")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _save(state: dict[str, Any]) -> dict[str, Any]:
    write_json(STATE_KEY, STATE_PATH, state)
    return state


def load_unattended_state() -> dict[str, Any]:
    value = read_json(STATE_KEY, STATE_PATH, {})
    return dict(value) if isinstance(value, dict) else {}


def _notify_failure_once(state: dict[str, Any], error: str) -> None:
    from notifier import send_pushover_alert

    fingerprint = str(error or "ukjent feil")[:240]
    previous = load_unattended_state()
    if previous.get("last_failure_fingerprint") == fingerprint:
        state["failure_notification"] = "DUPLIKAT_HOPPET_OVER"
        return
    ok, detail = send_pushover_alert(
        "Den automatiske rapportkontrollen feilet. Åpne Drift/Scheduler for detaljer.\n"
        f"Feil: {fingerprint}",
        title="⚠️ Planlagt rapport feilet",
    )
    state["failure_notification"] = "SENDT" if ok else f"FEILET: {detail or 'ukjent feil'}"
    state["last_failure_fingerprint"] = fingerprint


def run_once() -> dict[str, Any]:
    started = _now()
    previous = load_unattended_state()
    state: dict[str, Any] = {
        "state": "RUNNING",
        "started_at": started,
        "completed_at": None,
        "scheduler": {},
        "report_repair": {},
        "error": "",
        "process": "scheduled_runner",
        "last_failure_fingerprint": previous.get("last_failure_fingerprint", ""),
    }
    _save(state)

    # Repair delivery artifacts, but never let this maintenance step block the
    # actual schedule check.
    try:
        from market_intelligence import restore_public_reports

        state["report_repair"] = {
            "state": "COMPLETED",
            "restored": int(restore_public_reports(limit=25) or 0),
        }
    except Exception as exc:
        state["report_repair"] = {"state": "FAILED", "error": str(exc)[:500]}

    try:
        from scheduler_background import run_scheduler_cycle

        scheduler = dict(run_scheduler_cycle() or {})
        state["scheduler"] = scheduler
        if scheduler.get("state") == "ERROR":
            raise RuntimeError(str(scheduler.get("error") or "Scheduler feilet uten feildetalj"))
        state["state"] = "COMPLETED"
    except Exception as exc:
        state["state"] = "FAILED"
        state["error"] = str(exc)[:1000]
        _notify_failure_once(state, state["error"])

    state["completed_at"] = _now()
    _save(state)
    return state


def main() -> int:
    state = run_once()
    print(json.dumps(state, ensure_ascii=False, indent=2, default=str))
    return 0 if state.get("state") == "COMPLETED" else 1


if __name__ == "__main__":
    raise SystemExit(main())
