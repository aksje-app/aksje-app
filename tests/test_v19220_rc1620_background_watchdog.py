from __future__ import annotations

import io
import json
from contextlib import nullcontext
from dataclasses import asdict
from zipfile import ZipFile

import manual_job_background as background
import market_intelligence as mi


def _memory_storage(monkeypatch):
    memory = {}

    def write_json(key, path, value):
        memory[key] = json.loads(json.dumps(value, default=str))

    def read_json(key, path, default):
        return json.loads(json.dumps(memory.get(key, default)))

    monkeypatch.setattr(background, "write_json", write_json)
    monkeypatch.setattr(background, "read_json", read_json)
    background._THREADS.clear()
    background._publish_runtime_snapshot({})
    return memory


class _LiveThread:
    def is_alive(self):
        return True


def test_live_heartbeat_cannot_hide_stalled_real_progress(monkeypatch):
    _memory_storage(monkeypatch)
    execution_id = "MBJ-RC1620-STALL"
    status = {
        "execution_id": execution_id,
        "state": "RUNNING",
        "active_stage": "PREFLIGHT",
        "worker_process_identity": background._PROCESS_IDENTITY,
        "last_progress_at": "2020-01-01T00:00:00+00:00",
        "updated_at": "2020-01-01T00:00:00+00:00",
        "heartbeat_at": background._now(),
    }
    background._THREADS[execution_id] = _LiveThread()
    background._write_status(status)

    reconciled = background.reconcile_orphaned_status(status)

    assert reconciled["state"] == "STALLED"
    assert reconciled["error_code"] == "STAGE_PROGRESS_TIMEOUT"
    assert reconciled["lease_revoked"] is True
    assert reconciled["partial_results_published"] is False
    assert not background.is_running(reconciled)


def test_snapshot_poll_runs_progress_watchdog(monkeypatch):
    _memory_storage(monkeypatch)
    execution_id = "MBJ-RC1620-POLL"
    background._THREADS[execution_id] = _LiveThread()
    background._publish_runtime_snapshot({
        "execution_id": execution_id,
        "state": "RUNNING",
        "active_stage": "PREFLIGHT",
        "worker_process_identity": background._PROCESS_IDENTITY,
        "last_progress_at": "2020-01-01T00:00:00+00:00",
        "heartbeat_at": background._now(),
    })

    snapshot = background.get_active_status_snapshot()

    assert snapshot["state"] == "STALLED"
    assert snapshot["ui_poll_source"] == "PROCESS_MEMORY"


def test_manual_release_is_terminal_and_preserves_data(monkeypatch):
    _memory_storage(monkeypatch)
    execution_id = "MBJ-RC1620-RELEASE"
    background._write_status({
        "execution_id": execution_id,
        "state": "STOP_REQUESTED",
        "active_stage": "MARKET_DATA",
        "report_path": "/reports/unchanged.pdf",
    })

    released = background.force_release(execution_id, requested_by="TEST")

    assert released["state"] == "STALLED"
    assert released["lease_revoked"] is True
    assert released["report_path"] == "/reports/unchanged.pdf"
    assert released["error_code"] == "MANUAL_STALE_LEASE_RELEASE"


def test_revoked_worker_cannot_publish_late_success(monkeypatch):
    _memory_storage(monkeypatch)
    execution_id = "MBJ-RC1620-LATE"
    accepted = background._now()
    background._write_status({
        "execution_id": execution_id,
        "state": "QUEUED",
        "phase": "START",
        "active_stage": "PREFLIGHT",
        "accepted_at": accepted,
        "updated_at": accepted,
        "heartbeat_at": accepted,
        "worker_process_identity": background._PROCESS_IDENTITY,
        "cancel_requested": False,
        "lease_revoked": False,
        "completed_steps": [],
    })
    monkeypatch.setattr(background, "background_execution", lambda execution_id: nullcontext())

    def fake_run_job(*args, **kwargs):
        background.force_release(execution_id, requested_by="WATCHDOG_TEST")
        return {"run_id": "MUST-NOT-PUBLISH", "candidates": []}

    monkeypatch.setattr(mi, "run_job", fake_run_job)
    job = mi.JobProfile(name="Watchdog-test", markets=["Norge"])

    background._worker(execution_id, asdict(job), "TEST", False)
    final = background.get_status(execution_id)

    assert final["state"] == "STALLED"
    assert final.get("run_id") != "MUST-NOT-PUBLISH"
    assert final["partial_results_published"] is False


def test_diagnostic_bundle_is_small_and_secret_free(monkeypatch):
    _memory_storage(monkeypatch)
    execution_id = "MBJ-RC1620-DIAG"
    background._write_status({
        "execution_id": execution_id,
        "state": "FAILED",
        "error_code": "TEST",
        "api_key": "SECRET-MUST-NOT-LEAK",
        "portfolio": {"private": True},
    })

    payload, filename = background.diagnostic_bundle(execution_id)
    with ZipFile(io.BytesIO(payload)) as archive:
        status = json.loads(archive.read("status.json"))

    assert filename.endswith(".zip")
    assert status["execution_id"] == execution_id
    assert "api_key" not in status
    assert "portfolio" not in status
    assert b"SECRET-MUST-NOT-LEAK" not in payload
