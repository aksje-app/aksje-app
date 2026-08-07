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
from runtime_dependencies import assert_runtime_dependencies

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
        "Den automatiske rapportkontrollen feilet. Åpne Drift/Planlegger for detaljer.\n"
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
        "currency_alerts": {},
        "report_repair": {},
        "report_revalidation": {},
        "error": "",
        "process": "scheduled_runner",
        "last_failure_fingerprint": previous.get("last_failure_fingerprint", ""),
    }
    _save(state)

    try:
        state["runtime_dependencies"] = assert_runtime_dependencies()
    except Exception as exc:
        state["state"] = "FAILED"
        state["error"] = str(exc)[:1000]
        state["completed_at"] = _now()
        _notify_failure_once(state, state["error"])
        return _save(state)

    # The due-job check is the primary purpose of this process and must run
    # before report repair, revalidation or other maintenance can consume the
    # cron execution window.
    try:
        from runtime_safety import scheduler_allowed
        scheduler_enabled, scheduler_reason = scheduler_allowed()
        state["scheduler_configuration"] = {
            "enabled": bool(scheduler_enabled), "reason": scheduler_reason,
            "execution_mode": "AUTHORITATIVE_UNATTENDED_CRON",
        }
        if not scheduler_enabled:
            raise RuntimeError(f"Autonomi-planleggeren er ikke aktivert for cron: {scheduler_reason}")
        from scheduler_background import run_scheduler_cycle

        scheduler = dict(run_scheduler_cycle(authoritative_unattended=True) or {})
        scheduler["execution_mode"] = "AUTHORITATIVE_UNATTENDED_CRON"
        state["scheduler"] = scheduler
        try:
            from market_intelligence import scheduler_health_snapshot
            state["scheduler_health"] = dict(scheduler_health_snapshot() or {})
        except Exception as health_exc:
            state["scheduler_health"] = {"state": "UNAVAILABLE", "error": str(health_exc)[:500]}
        if scheduler.get("state") == "ERROR":
            raise RuntimeError(str(scheduler.get("error") or "Planlegger feilet uten feildetalj"))
        state["state"] = "COMPLETED"
    except Exception as exc:
        state["state"] = "FAILED"
        state["error"] = str(exc)[:1000]
        _notify_failure_once(state, state["error"])

    # Currency alerts share the durable five-minute Render cron. They run
    # independently of report due-times, market hours and user login.
    try:
        from currency_alert_service import run_currency_alert_checks

        fx_rows = list(run_currency_alert_checks(force=False, source="scheduled_cron") or [])
        fx_errors = [row for row in fx_rows if row.get("status") == "error"]
        state["currency_alerts"] = {
            "state": "DEGRADED" if fx_errors else "COMPLETED",
            "checked": len(fx_rows),
            "sent": sum(1 for row in fx_rows if row.get("sent")),
            "errors": [str(row.get("error") or "")[:240] for row in fx_errors],
        }
    except Exception as exc:
        # A provider failure must be visible, but must not suppress scheduled reports.
        state["currency_alerts"] = {"state": "FAILED", "error": str(exc)[:500]}

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

    # Provisional reports are rerun as immutable revisions after their waiting
    # interval. Revalidation has its own budget reserve and can never block the
    # ordinary scheduler.
    try:
        from market_intelligence import revalidate_provisional_reports

        state["report_revalidation"] = dict(revalidate_provisional_reports(limit=1) or {})
    except Exception as exc:
        state["report_revalidation"] = {"state": "FAILED", "error": str(exc)[:500]}

    state["completed_at"] = _now()
    _save(state)
    return state


def main() -> int:
    state = run_once()
    print(json.dumps(state, ensure_ascii=False, indent=2, default=str))
    return 0 if state.get("state") == "COMPLETED" else 1


if __name__ == "__main__":
    raise SystemExit(main())
