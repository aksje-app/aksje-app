from __future__ import annotations

from datetime import datetime, timezone

import cron_control
import execution_coordination
import paper_scanner_runtime
from autonomi_core.runtime.full_execution import build_full_execution_receipt


def _receipt_run(chain):
    return {
        "run_id": "R1", "mission_id": "M1", "configuration_version": "C1",
        "portfolio_need_preflight": {"read_at": "now", "context": {"ok": True}},
        "discovery_data": {"markets": ["USA"]}, "markets": ["USA"],
        "candidates": [{"investment_score": 70, "strategy_scores": {"a": 1}}],
        "canonical_top_picks": {"published": True, "result_id": "X", "top_picks": []},
        "portfolio_decisions": {"decisions": [{"portfolio_assessed": True}]},
        "autonomous_chain": chain,
        "persistence": {"ok": True}, "pdf_delivery": {"required": False},
        "notification": {"sent": True, "required": True},
        "canonical_result": {"stored_once": True, "result_id": "X"},
        "historical_learning": {"snapshots_created": 1},
    }


def test_paper_and_report_locks_are_distinct():
    assert paper_scanner_runtime.PAPER_SCANNER_ADVISORY_LOCK_ID != execution_coordination._REPORT_EXECUTION_LOCK_ID


def test_theoretical_stage_survives_unrelated_controlled_learning_error():
    run = _receipt_run({
        "status": "COMPLETED_WITH_ERRORS", "execution": "THEORETICAL_ONLY",
        "stages": [
            {"name": "AUTONOMOUS_PORTFOLIO", "status": "OK", "detail": {"decisions": 10}},
            {"name": "CONTROLLED_LEARNING", "status": "ERROR", "detail": {"error": "later failure"}},
        ],
    })
    receipt = build_full_execution_receipt(run)
    stage = next(row for row in receipt["stages"] if row["code"] == "THEORETICAL_DECISIONS")
    assert stage["status"] == "OK"
    assert stage["evidence"]["decisions"] == 10


def test_blocked_theoretical_decision_still_fails_closed():
    run = _receipt_run({
        "status": "OK", "execution": "THEORETICAL_ONLY",
        "stages": [{"name": "AUTONOMOUS_PORTFOLIO", "status": "BLOCKED", "detail": {"reason": "integrity"}}],
    })
    receipt = build_full_execution_receipt(run)
    assert "THEORETICAL_DECISIONS" in receipt["failed_stages"]


def test_market_closed_heartbeat_does_not_replace_last_successful_scan(monkeypatch):
    monkeypatch.setattr(cron_control, "_utc_now", lambda: datetime(2026, 8, 12, 12, 5, tzinfo=timezone.utc))
    monkeypatch.setattr(cron_control, "load_settings", lambda: {
        "last_scan_at": "2026-08-12T10:00:00+00:00", "scan_interval_minutes": 30,
        "background_scanning_enabled": True,
    })
    monkeypatch.setattr(paper_scanner_runtime, "load_scanner_status", lambda: {
        "state": "MARKET_CLOSED", "heartbeat_at": "2026-08-12T12:00:00+00:00",
        "completed_at": "2026-08-12T12:00:00+00:00",
        "last_successful_scan_at": "2026-08-12T10:00:00+00:00",
    })
    status = cron_control.cron_status_text()
    assert status["last_scan_at"] == "2026-08-12T10:00:00+00:00"
    assert status["scanner_state"] == "MARKET_CLOSED"
    assert status["scanner_worker_healthy"] is True
