from __future__ import annotations

import io
import json
import zipfile
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import manual_job_background as bg


def test_autonomy_timeout_is_fifteen_minutes_and_fresh_progress_keeps_lease():
    assert bg._stage_progress_limit("AUTONOMOUS") == 900
    now = datetime.now(timezone.utc)
    status = {
        "execution_id": "E-FRESH", "state": "RUNNING", "active_stage": "AUTONOMOUS",
        "last_progress_at": (now - timedelta(seconds=899)).isoformat(),
        "worker_process_identity": bg._PROCESS_IDENTITY,
    }
    with patch.object(bg, "_thread_is_alive", return_value=True):
        result = bg.reconcile_orphaned_status(status)
    assert result["state"] == "RUNNING"


def test_autonomy_silence_beyond_limit_revokes_lease():
    now = datetime.now(timezone.utc)
    status = {
        "execution_id": "E-STALE", "state": "RUNNING", "active_stage": "AUTONOMOUS",
        "last_progress_at": (now - timedelta(seconds=901)).isoformat(),
        "worker_process_identity": bg._PROCESS_IDENTITY,
    }
    with patch.object(bg, "_thread_is_alive", return_value=True), \
         patch.object(bg, "_write_status", side_effect=lambda value: dict(value)):
        result = bg.reconcile_orphaned_status(status)
    assert result["state"] == "STALLED"
    assert result["lease_revoked"] is True
    assert result["error_code"] == "STAGE_PROGRESS_TIMEOUT"


def test_diagnostic_marks_unmatched_acceptance_as_previous_run():
    status = {"execution_id": "E-NEW", "state": "STALLED", "run_id": ""}
    diagnostics = {"acceptance": {"verdict": "PASS", "report_id": "MI-OLD"}}
    with patch.object(bg, "get_status", return_value=status), \
         patch("learning_acceptance.build_learning_diagnostics", return_value=diagnostics), \
         patch("report_test_mode.load_report_test_mode", return_value={"enabled": False}), \
         patch("scheduled_runner.load_unattended_state", return_value={}):
        payload, _ = bg.diagnostic_bundle("E-NEW")
    with zipfile.ZipFile(io.BytesIO(payload)) as archive:
        acceptance = json.loads(archive.read("learning/LEARNING_ACCEPTANCE.json"))
    assert acceptance["current_job_match"] is False
    assert acceptance["evidence_scope"] == "PREVIOUS_RUN"
    assert acceptance["diagnostic_execution_id"] == "E-NEW"


def test_runtime_gateway_forwards_progress_callback():
    from autonomi_core.runtime.orchestrator import execute_market_mission

    events = []
    callback = events.append
    fake_result = {"status": "OK", "stages": []}
    run = {"run_id": "MI-CALLBACK", "candidates": [], "proposals": []}
    with patch("autonomous_orchestrator.run_post_scan_chain", return_value=fake_result) as chain:
        execute_market_mission(run, progress_callback=callback)
    assert chain.call_args.kwargs["progress_callback"] is callback


def test_portfolio_source_contains_cancellable_internal_checkpoints():
    from pathlib import Path
    source = (Path(__file__).resolve().parents[1] / "autonomous_portfolio.py").read_text(encoding="utf-8")
    for label in (
        "Markedssnapshot er lagret", "Parallelle strategier er vurdert",
        "Eksisterende læringsposisjoner er oppdatert",
        "Kjøps- og læringsbeslutninger er ferdige",
        "Porteføljer, beslutninger og ytelse er lagret",
        "Synkroniserer delte strategi- og læringskontoer",
        "Bygger uforanderlig replay- og revisjonsspor",
    ):
        assert label in source
