from __future__ import annotations

from pathlib import Path

from app_version import APP_VERSION
from autonomous_portfolio import _normalise_runtime_positions
from autonomi_core.runtime.full_execution import pre_notification_gate


def _base_run():
    candidate = {"ticker": "TEST.OL", "investment_score": 70, "strategy_scores": {"Quality": 70}}
    return {
        "run_id": "RC1631", "mission_id": "M1", "configuration_version": "C1",
        "market_runs": [{"market": "Norge"}], "discovery_data": {"markets": ["Norge"]},
        "candidates": [candidate], "changes": {"new": [candidate]},
        "portfolio_need_preflight": {"read_at": "2026-08-09T00:00:00+00:00", "context": {"position_count": 0}, "position_count": 0},
        "portfolio_decisions": {"portfolio_context": {}, "decisions": [{"ticker": "TEST.OL", "portfolio_assessed": True}]},
        "autonomous_chain": {"status": "OK", "execution": "THEORETICAL_ONLY", "stages": [{"name": "AUTONOMOUS_PORTFOLIO", "status": "OK"}]},
        "persistence": {"ok": True}, "canonical_result": {"stored_once": True, "result_id": "R1"},
        "historical_learning": {"snapshots_created": 0}, "pdf_delivery": {"required": False},
    }


def test_version():
    assert APP_VERSION == "v19.22.0-rc16.31"


def test_null_runtime_position_numbers_are_normalised():
    rows = _normalise_runtime_positions({"X": {"quantity": None, "average_price": None, "highest_price": None, "observation_horizon_days": None}})
    assert rows["X"]["quantity"] == 0.0
    assert rows["X"]["average_price"] == 0.0
    assert rows["X"]["highest_price"] == 0.0
    assert rows["X"]["observation_horizon_days"] == 60.0


def test_notification_gate_blocks_autonomy_error():
    run = _base_run()
    run["autonomous_chain"] = {"status": "ERROR", "stages": [], "errors": ["TypeError"]}
    result = pre_notification_gate(run)
    assert result["ok"] is False
    assert "THEORETICAL_DECISIONS" in result["failed_stages"]


def test_notification_gate_accepts_complete_pre_delivery_chain():
    assert pre_notification_gate(_base_run())["ok"] is True


def test_terminal_status_is_not_published_by_progress_callback():
    source = Path("manual_job_background.py").read_text(encoding="utf-8")
    assert 'if phase == "COMPLETE":\n                completed_steps = list(_STAGE_ORDER)' not in source
    assert '"completed_steps": list(_STAGE_ORDER)' in source
    assert '"run_id": str(failed_result.get("run_id")' in source


def test_autonomy_error_keeps_traceback():
    source = Path("autonomous_orchestrator.py").read_text(encoding="utf-8")
    assert '"traceback": traceback.format_exc()[-12000:]' in source
