"""One-shot unattended scheduler entry point for Render Cron Jobs.

This process has no Streamlit or login dependency. It records a durable
heartbeat, repairs public reports independently, and then runs the coordinated
due-job check. A report-repair failure can never suppress a scheduled scan.
"""
from __future__ import annotations

import json
import logging
import os
import time
from datetime import datetime, timezone
from typing import Any

from durable_runtime import read_json, write_json
from storage_architecture import runtime_data_path
from runtime_dependencies import assert_runtime_dependencies

STATE_KEY = "scheduler/unattended_state.json"
STATE_PATH = runtime_data_path("scheduler", "unattended_state.json")
RECOVERY_PATH = runtime_data_path("scheduler", "unattended_recovery.json")


def _configure_headless_logging() -> None:
    """Keep expected Streamlit bare-mode warnings out of cron diagnostics."""
    for name in (
        "streamlit.runtime.scriptrunner_utils.script_run_context",
        "streamlit.runtime.state.session_state_proxy",
    ):
        logging.getLogger(name).setLevel(logging.ERROR)
    # Some Streamlit imports reset their logger levels after startup.  A record
    # factory is stable for the lifetime of this headless process and only
    # demotes the two known, harmless bare-mode warnings; real warnings remain.
    if not getattr(logging, "_ai_headless_record_factory_installed", False):
        original_factory = logging.getLogRecordFactory()

        def _headless_record_factory(*args, **kwargs):
            record = original_factory(*args, **kwargs)
            if (
                str(record.name).startswith("streamlit.runtime.")
                and (
                    "missing ScriptRunContext" in record.getMessage()
                    or "Session state does not function" in record.getMessage()
                )
            ):
                record.levelno = logging.DEBUG
                record.levelname = "DEBUG"
            return record

        logging.setLogRecordFactory(_headless_record_factory)
        logging._ai_headless_record_factory_installed = True


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _save(state: dict[str, Any]) -> dict[str, Any]:
    last_error: Exception | None = None
    retry_delays = (1.0, 2.0, 4.0, 8.0, 15.0)
    for attempt in range(1, len(retry_delays) + 2):
        try:
            write_json(STATE_KEY, STATE_PATH, state)
            state["persistence_receipt"] = {
                "state": "PERSISTED", "attempts": attempt, "at": _now(),
            }
            return state
        except Exception as exc:
            last_error = exc
            if attempt <= len(retry_delays):
                time.sleep(retry_delays[attempt - 1])
    # A final status write must not turn otherwise completed work into an
    # untraceable status-1 crash during a short PostgreSQL recovery.  Keep a
    # local recovery receipt which the next healthy cron republishes.
    receipt = {
        "state": "PENDING_DATABASE_REPLAY", "at": _now(),
        "error": f"{type(last_error).__name__}: {str(last_error)[:1000]}",
        "payload": state,
    }
    RECOVERY_PATH.parent.mkdir(parents=True, exist_ok=True)
    temp = RECOVERY_PATH.with_suffix(".tmp")
    temp.write_text(json.dumps(receipt, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    os.replace(temp, RECOVERY_PATH)
    state["persistence_receipt"] = {
        "state": "PENDING_DATABASE_REPLAY", "attempts": len(retry_delays) + 1,
        "at": receipt["at"], "error": receipt["error"],
    }
    return state


def _database_preflight(attempts: int = 3) -> dict[str, Any]:
    """Require consecutive healthy probes before analyses or trades begin."""
    from services.storage_service import get_storage_service
    checks: list[dict[str, Any]] = []
    for attempt in range(1, max(2, int(attempts)) + 1):
        health = get_storage_service().health().to_dict()
        production_database_required = bool(os.getenv("DATABASE_URL", "").strip())
        probe_ok = bool(health.get("ok")) and (
            not production_database_required or str(health.get("backend") or "").lower() == "postgres"
        )
        checks.append({"attempt": attempt, "ok": probe_ok, "backend": health.get("backend"), "message": str(health.get("message") or "")[:500]})
        if not probe_ok:
            return {"state": "DEFERRED_DATABASE", "ready": False, "checks": checks}
        if attempt < attempts:
            time.sleep(1.0)
    return {"state": "READY", "ready": True, "checks": checks}


def _replay_recovery_receipt() -> dict[str, Any]:
    if not RECOVERY_PATH.is_file():
        return {"state": "NOT_NEEDED"}
    try:
        receipt = json.loads(RECOVERY_PATH.read_text(encoding="utf-8"))
        payload = receipt.get("payload") if isinstance(receipt, dict) else None
        if isinstance(payload, dict):
            write_json(STATE_KEY, STATE_PATH, payload)
        RECOVERY_PATH.unlink(missing_ok=True)
        return {"state": "REPLAYED", "original_at": receipt.get("at") if isinstance(receipt, dict) else ""}
    except Exception as exc:
        return {"state": "FAILED", "error": f"{type(exc).__name__}: {str(exc)[:500]}"}




def _exception_chain_text(exc: Exception | str) -> str:
    """Flatten an exception chain so wrapped PostgreSQL recovery stays classifiable."""
    if not isinstance(exc, BaseException):
        return str(exc or "").lower()
    parts: list[str] = []
    current: BaseException | None = exc
    seen: set[int] = set()
    while current is not None and id(current) not in seen:
        seen.add(id(current))
        parts.append(f"{type(current).__name__}: {current}")
        current = current.__cause__ or current.__context__
    return " | ".join(parts).lower()


def _is_transient_storage_error(exc: Exception | str) -> bool:
    text = _exception_chain_text(exc)
    markers = (
        "recovery mode", "not yet accepting connections", "consistent recovery",
        "database system is in recovery", "database system is not yet accepting",
        "connection reset", "connection refused", "server closed the connection",
        "terminating connection", "storageunavailableerror", "could not connect",
        "connection to server",
    )
    return any(marker in text for marker in markers)


def _scanner_failure_state(exc: Exception) -> dict[str, Any]:
    """Report storage-finalization failures without pretending analysis failed."""
    result: dict[str, Any] = {
        "state": "FAILED",
        "execution_mode": "SEQUENTIAL_SHARED_2GB_SCHEDULER",
        "error": f"{type(exc).__name__}: {str(exc)[:500]}",
    }
    checkpoint: dict[str, Any] = {}
    try:
        from paper_scanner_runtime import load_scanner_status, load_scanner_checkpoint
        scanner_status = dict(load_scanner_status() or {})
        checkpoint = dict(load_scanner_checkpoint() or {})
    except Exception:
        # PostgreSQL may be in recovery precisely while we are classifying the
        # failure. The local files are diagnostic mirrors from the last
        # successful durable write and may be read only for classification;
        # they are never used as authoritative trading state.
        scanner_status = {}
        try:
            from paper_scanner_runtime import PAPER_SCANNER_STATUS_PATH, PAPER_SCANNER_CHECKPOINT_PATH
            if PAPER_SCANNER_STATUS_PATH.is_file():
                scanner_status = dict(json.loads(PAPER_SCANNER_STATUS_PATH.read_text(encoding="utf-8")) or {})
            if PAPER_SCANNER_CHECKPOINT_PATH.is_file():
                checkpoint = dict(json.loads(PAPER_SCANNER_CHECKPOINT_PATH.read_text(encoding="utf-8")) or {})
        except Exception:
            checkpoint = {}
    processed = int(scanner_status.get("tickers_processed") or checkpoint.get("next_index") or 0)
    total = int(scanner_status.get("tickers_total") or len(checkpoint.get("tickers") or []) or 0)
    phase = str(scanner_status.get("phase") or checkpoint.get("phase") or "").upper()
    result.update({
        "scan_run_id": str(scanner_status.get("scan_run_id") or ""),
        "tickers_processed": processed,
        "tickers_total": total,
        "phase": phase,
    })
    if _is_transient_storage_error(exc):
        if total > 0 and processed >= total:
            result["state"] = "FINALIZATION_PENDING_STORAGE"
            result["analysis_completed"] = True
            result["recovery_action"] = "Neste cron gjenopptar sluttbehandling uten ny tickeranalyse."
        else:
            result["state"] = "DEFERRED_DATABASE"
            result["analysis_completed"] = False
            result["recovery_action"] = "Neste cron fortsetter fra siste autoritative checkpoint når PostgreSQL er skriveklar."
    return result


def _derive_overall_state(state: dict[str, Any]) -> str:
    """Derive a truthful cron result from critical and maintenance subsystems."""
    current = str(state.get("state") or "")
    if current in {"FAILED", "BLOCKED_DEPLOY_MISMATCH", "DEFERRED_DATABASE"}:
        return current
    scanner = str((state.get("paper_scanner") or {}).get("state") or "")
    if scanner == "PARTIAL_CHECKPOINT":
        return "PARTIAL_CHECKPOINT"
    if scanner == "FINALIZATION_PENDING_STORAGE":
        return "DEGRADED_STORAGE"
    if scanner == "DEFERRED_DATABASE":
        return "DEFERRED_DATABASE"
    if scanner in {"FAILED", "FAILED_STORAGE"}:
        return "FAILED"
    warnings = []
    for key, field in (
        ("learning_observation_maintenance", "status"),
        ("report_repair", "state"),
        ("report_revalidation", "state"),
        ("storage_retention", "state"),
        ("report_delivery_retry", "state"),
        ("required_reports", "state"),
    ):
        value = str((state.get(key) or {}).get(field) or "").upper()
        if value in {"FAILED", "BLOCKED_DATABASE"}:
            warnings.append(f"{key}:{value}")
    state["degraded_components"] = warnings
    return "COMPLETED_WITH_WARNINGS" if warnings else "COMPLETED"


def _production_closure_snapshot(state: dict[str, Any]) -> dict[str, Any]:
    """Compact live acceptance evidence emitted on every cron."""
    retention = dict(state.get("storage_retention") or {})
    scanner = dict(state.get("paper_scanner") or {})
    checks = {
        "database_preflight": bool((state.get("database_preflight") or {}).get("ready")),
        "runtime_identity": bool((state.get("runtime_alignment") or {}).get("aligned")),
        "cluster_identity": bool((state.get("cluster_alignment") or {}).get("aligned")),
        "retention_apply_requested": retention.get("apply_requested") is True,
        "retention_effective": retention.get("apply_enabled") is True and str(retention.get("state") or "") in {"PARTIAL", "COMPLETED"},
        "scanner_not_failed": str(scanner.get("state") or "") not in {"FAILED", "FAILED_STORAGE"},
        "no_unresolved_storage_finalization": str(scanner.get("state") or "") != "FINALIZATION_PENDING_STORAGE",
        "no_degraded_components": not list(state.get("degraded_components") or []),
    }
    blockers = [name for name, ok in checks.items() if not ok]
    return {
        "state": "CRON_ACCEPTED" if not blockers else "CRON_NOT_ACCEPTED",
        "checks": checks,
        "blockers": blockers,
        "note": "Produksjonsstatus krever i tillegg komplett 08:00/14:00/22:00-sekvens og leveringsbevis.",
    }

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


def _maintenance_due(previous: dict[str, Any], key: str, *, default_minutes: int) -> bool:
    raw = str((previous.get(key) or {}).get("completed_at") or "").strip()
    if not raw:
        return True
    try:
        last = datetime.fromisoformat(raw.replace("Z", "+00:00"))
        interval = max(5, int(os.getenv("REPORT_MAINTENANCE_INTERVAL_MINUTES", str(default_minutes)) or default_minutes))
        return (datetime.now(timezone.utc) - last.astimezone(timezone.utc)).total_seconds() >= interval * 60
    except Exception:
        return True


def _run_once_locked() -> dict[str, Any]:
    _configure_headless_logging()
    from runtime_identity import publish_runtime_identity, validate_cluster_alignment, validate_expected_runtime
    started = _now()
    previous = load_unattended_state()
    state: dict[str, Any] = {
        "state": "RUNNING",
        "started_at": started,
        "completed_at": None,
        "scheduler": {},
        "report_test_mode": {},
        "currency_alerts": {},
        "learning_observation_maintenance": {},
        "report_repair": {},
        "report_revalidation": {},
        "error": "",
        "process": "scheduled_runner",
        "last_failure_fingerprint": previous.get("last_failure_fingerprint", ""),
        "memory_observations": [],
    }
    from runtime_memory import memory_guard
    def _mem(label: str, *, stop: bool = True):
        observation = memory_guard(label, raise_on_pressure=False)
        state["memory_observations"].append(observation)
        if stop and observation.get("pressure"):
            state.update({"state":"MEMORY_DEFERRED","completed_at":_now(),"error":f"Memory soft limit reached before {label}: {observation.get('observed_mb')} MB"})
            _save(state)
            from runtime_memory import MemoryPressureError
            raise MemoryPressureError(state["error"])
        return observation
    _mem("scheduler:start", stop=False)
    _save(state)

    state["database_preflight"] = _database_preflight()
    if not state["database_preflight"].get("ready"):
        state.update({
            "state": "DEFERRED_DATABASE", "completed_at": _now(),
            "error": "PostgreSQL er ikke stabilt skriveklar; hele kjøringen er utsatt uten analyse eller handel.",
        })
        return _save(state)
    state["database_recovery_replay"] = _replay_recovery_receipt()

    state["runtime_identity"] = publish_runtime_identity("report_scheduler")
    aligned, alignment_reason = validate_expected_runtime()
    state["runtime_alignment"] = {"aligned": aligned, "reason": alignment_reason}
    if not aligned:
        state["state"] = "FAILED"
        state["error"] = alignment_reason
        state["completed_at"] = _now()
        _notify_failure_once(state, alignment_reason)
        return _save(state)
    cluster_aligned, cluster_reason = validate_cluster_alignment("report_scheduler", ("web",))
    state["cluster_alignment"] = {"aligned": cluster_aligned, "reason": cluster_reason}
    if not cluster_aligned:
        state["state"] = "BLOCKED_DEPLOY_MISMATCH"
        state["error"] = cluster_reason
        state["completed_at"] = _now()
        _notify_failure_once(state, cluster_reason)
        return _save(state)

    try:
        state["runtime_dependencies"] = assert_runtime_dependencies()
    except Exception as exc:
        state["state"] = "FAILED"
        state["error"] = str(exc)[:1000]
        state["completed_at"] = _now()
        _notify_failure_once(state, state["error"])

        return _save(state)

    _mem("scheduler:before_due_jobs")

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

        # Claim only the short report-scheduler section with the scheduler
        # advisory lock.  Paper scanning has its own lock and may take several
        # minutes; holding the report lock around that work previously made a
        # due 08/14/22 report wait for the following cron cycle.
        scheduler = dict(run_scheduler_cycle(authoritative_unattended=True, already_coordinated=False) or {})
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

    _mem("scheduler:after_due_jobs")

    # The bounded acceptance mode runs only when no ordinary report was claimed
    # in this cron cycle. It uses the same report execution lock. Any positions
    # created are isolated LEARNING_ONLY observations; real trading is impossible.
    try:
        if state.get("state") == "COMPLETED" and int((state.get("scheduler") or {}).get("runs") or 0) == 0:
            from report_test_mode import run_due_report_test
            state["report_test_mode"] = dict(run_due_report_test() or {})
        else:
            state["report_test_mode"] = {"run_state": "SKIPPED_ORDINARY_REPORT"}
    except Exception as exc:
        state["report_test_mode"] = {"run_state": "FAILED", "error": str(exc)[:500]}

    _mem("scheduler:after_report_test")

    # Retry only delivery artifacts from an already stored run. Market scan,
    # Autonomy and learning are never repeated by this step.
    try:
        from market_intelligence import retry_pending_required_report_deliveries
        state["report_delivery_retry"] = dict(retry_pending_required_report_deliveries() or {})
    except Exception as exc:
        state["report_delivery_retry"] = {"state": "FAILED", "error": str(exc)[:500]}

    # Required-report accounting is independent of report generation. It can
    # warn about a missing report even when the report pipeline itself failed.
    try:
        from market_intelligence import notify_overdue_required_reports
        state["required_reports"] = dict(notify_overdue_required_reports() or {})
    except Exception as exc:
        state["required_reports"] = {"state": "FAILED", "error": str(exc)[:500]}

    _mem("scheduler:before_currency_alerts")

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

    _mem("scheduler:before_scanner")

    # Paper scanning is intentionally owned by this 2 GiB scheduler service.
    # Reports and scanning run sequentially, never in parallel, so the already
    # allocated Standard memory can be reused without reducing ticker, market
    # or source coverage.  Paper's advisory lock remains a final duplicate-
    # execution guard during the one-time retirement of a legacy scanner cron.
    try:
        from runtime_memory import release_process_memory
        before_scan = release_process_memory("scheduled_runner:before_paper_scanner")
        from scanner_worker import run_once as run_paper_scanner
        trades = int(run_paper_scanner(force=False, check_currency_alerts=False) or 0)
        from paper_scanner_runtime import load_scanner_status
        scanner_status = dict(load_scanner_status() or {})
        state["paper_scanner"] = {
            "state": str(scanner_status.get("state") or "COMPLETED"),
            "execution_mode": "SEQUENTIAL_SHARED_2GB_SCHEDULER",
            "trades": trades,
            "scan_run_id": str(scanner_status.get("scan_run_id") or ""),
            "tickers_processed": int(scanner_status.get("tickers_processed") or 0),
            "tickers_total": int(scanner_status.get("tickers_total") or 0),
            "memory_before_scan": before_scan.get("after"),
            "memory": scanner_status.get("memory"),
            "memory_policy": scanner_status.get("memory_policy"),
            "memory_pressure_reason": str(scanner_status.get("memory_pressure_reason") or ""),
            "markets_open": list(scanner_status.get("markets_open") or []),
            "cooldown_started_at": scanner_status.get("cooldown_started_at"),
            "error": str(scanner_status.get("error") or "")[:500],
        }
    except Exception as exc:
        state["paper_scanner"] = _scanner_failure_state(exc)

    _mem("scheduler:after_scanner")

    # Learning maintenance is non-time-critical. It intentionally runs after
    # the Paper scanner so a long observation-maintenance pass can never delay
    # a due 15-minute market scan by tens of minutes.
    try:
        from runtime_memory import release_process_memory
        release_process_memory("scheduled_runner:before_learning_observations")
        from learning_observation_engine import run_learning_maintenance
        state["learning_observation_maintenance"] = dict(run_learning_maintenance() or {})
    except Exception as exc:
        state["learning_observation_maintenance"] = {"status":"FAILED","error":f"{type(exc).__name__}: {str(exc)[:500]}","production_changed":False}

    _mem("scheduler:after_learning")

    # Repair delivery artifacts, but never let this maintenance step block the
    # actual schedule check.
    if _maintenance_due(previous, "report_repair", default_minutes=360):
        try:
            from market_intelligence import restore_public_reports

            state["report_repair"] = {
                "state": "COMPLETED", "completed_at": _now(),
                "restored": int(restore_public_reports(limit=25) or 0),
            }
        except Exception as exc:
            state["report_repair"] = {"state": "FAILED", "completed_at": _now(), "error": str(exc)[:500]}
    else:
        state["report_repair"] = {**dict(previous.get("report_repair") or {}), "state": "NOT_DUE"}

    # Provisional reports are rerun as immutable revisions after their waiting
    # interval. Revalidation has its own budget reserve and can never block the
    # ordinary scheduler.
    if _maintenance_due(previous, "report_revalidation", default_minutes=360):
        try:
            from market_intelligence import revalidate_provisional_reports, revalidation_blackout_status

            blackout = revalidation_blackout_status()
            state["report_revalidation"] = {
                **dict(blackout if blackout.get("blocked") else revalidate_provisional_reports(limit=1) or {}),
                "completed_at": _now(),
            }
        except Exception as exc:
            state["report_revalidation"] = {"state": "FAILED", "completed_at": _now(), "error": str(exc)[:500]}
    else:
        state["report_revalidation"] = {**dict(previous.get("report_revalidation") or {}), "state": "NOT_DUE"}

    _mem("scheduler:before_retention")

    retention_previous = dict(previous.get("storage_retention") or {})
    retention_previous_state = str(retention_previous.get("state") or "")
    try:
        from storage_retention import retention_apply_enabled
        retention_env_enabled = bool(retention_apply_enabled())
    except Exception:
        retention_env_enabled = False
    # If Render is switched from DRY_RUN to APPLY, do not wait up to 24 hours:
    # run the first bounded delete batch on the very next cron.
    retention_just_enabled = retention_env_enabled and retention_previous.get("apply_enabled") is not True
    retention_due = (
        retention_just_enabled
        or retention_previous_state in {"PARTIAL", "FAILED", "BLOCKED_DATABASE"}
        or _maintenance_due(previous, "storage_retention", default_minutes=1440)
    )
    if retention_due:
        try:
            from storage_retention import run_storage_retention
            state["storage_retention"] = dict(run_storage_retention() or {})
        except Exception as exc:
            state["storage_retention"] = {"state": "FAILED", "completed_at": _now(), "error": str(exc)[:500]}
    else:
        state["storage_retention"] = {**dict(previous.get("storage_retention") or {}), "state": "NOT_DUE"}

    _mem("scheduler:complete", stop=False)
    state["completed_at"] = _now()
    state["state"] = _derive_overall_state(state)
    state["production_closure"] = _production_closure_snapshot(state)
    _save(state)
    return state


def run_once() -> dict[str, Any]:
    """Run one cron cycle with a controlled memory-pressure exit."""
    try:
        return _run_once_locked()
    except Exception as exc:
        from runtime_memory import MemoryPressureError
        if not isinstance(exc, MemoryPressureError):
            raise
        try:
            state = load_unattended_state()
        except Exception:
            state = {}
        state.update({
            "state": "MEMORY_DEFERRED", "completed_at": _now(),
            "error": str(exc)[:1000], "process": "scheduled_runner",
        })
        try: _save(state)
        except Exception: pass
        return state


def main() -> int:
    state = run_once()
    summary = {
        "state": state.get("state"), "started_at": state.get("started_at"),
        "completed_at": state.get("completed_at"), "error": state.get("error"),
        "scheduled_runs": (state.get("scheduler") or {}).get("runs", 0),
        "report_test_mode": (state.get("report_test_mode") or {}).get("run_state"),
        "currency_alerts": (state.get("currency_alerts") or {}).get("state"),
        "learning_observations": (state.get("learning_observation_maintenance") or {}).get("status"),
        "report_repair": (state.get("report_repair") or {}).get("state"),
        "report_revalidation": (state.get("report_revalidation") or {}).get("state"),
        "paper_scanner": (state.get("paper_scanner") or {}).get("state"),
    }
    print(json.dumps(summary, ensure_ascii=False, default=str))
    return 0 if state.get("state") in {
        "COMPLETED", "COMPLETED_WITH_WARNINGS", "PARTIAL_CHECKPOINT",
        "DEFERRED_DATABASE", "DEGRADED_STORAGE", "MEMORY_DEFERRED",
    } else 1


if __name__ == "__main__":
    raise SystemExit(main())
