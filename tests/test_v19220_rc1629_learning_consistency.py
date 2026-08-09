from __future__ import annotations

from unittest.mock import patch

from app_version import APP_VERSION
from learning_acceptance import evaluate_learning_run
from report_integrity import audit_learning_report_consistency


def _diagnostic_shape() -> dict:
    trades = [
        {"trade_id": f"LT-{index}", "ticker": ticker, "action": "BUY", "mode": "LEARNING_ONLY"}
        for index, ticker in enumerate(("AAA.OL", "BBB.ST", "CCC"), 1)
    ]
    return {
        "run_id": "MI-20260809-094723",
        "autonomous_chain": {
            "status": "OK",
            "autonomy_learning_account": {"fills": [], "account_metrics": {}},
            "learning_trades": trades,
            "stages": [{
                "name": "AUTONOMOUS_PORTFOLIO",
                "detail": {"learning_buys": 3, "learning_open_positions": 31, "learning_fills": []},
            }],
        },
    }


def test_version_is_rc1630():
    assert APP_VERSION == "v19.22.0-rc16.30"


def test_action_buy_is_normalised_when_shared_fills_are_empty():
    audit = audit_learning_report_consistency(_diagnostic_shape())
    assert audit["ok"] is True
    assert audit["learning_buys"] == 3
    assert audit["learning_open_positions"] == 31


def test_side_buy_remains_supported_for_shared_account():
    run = _diagnostic_shape()
    run["autonomous_chain"]["autonomy_learning_account"] = {
        "fills": [{"trade_id": "SF-1", "ticker": "AAA.OL", "side": "BUY"}],
        "account_metrics": {"open_positions": 1},
    }
    run["autonomous_chain"]["stages"][0]["detail"].update({"learning_buys": 1, "learning_open_positions": 1})
    audit = audit_learning_report_consistency(run)
    assert audit["ok"] is True
    assert audit["learning_buys"] == 1


def test_observe_is_explained_outcome_not_unclassified_blocker():
    run = {
        "run_id": "MI-OBSERVE", "report_id": "MI-OBSERVE",
        "candidates": [{"ticker": "WAIT.OL"}],
        "autonomous_chain": {
            "status": "OK",
            "learning_portfolio": {"last_run_id": "MI-OBSERVE", "positions": {"WAIT.OL": {}}},
            "learning_decisions": [{
                "ticker": "WAIT.OL", "action": "OBSERVE",
                "reason": "Ikke med i dagens kandidatsett; siste markering beholdes",
            }],
            "learning_trades": [], "learning_performance": {"observation_count": 1},
        },
    }
    with patch("learning_acceptance.write_json"):
        result = evaluate_learning_run(run)
    assert result["decision_trace"][0]["first_blocker_code"] == "NONE"
    assert result["blocker_counts"] == []


def test_worker_failure_is_terminal_and_thread_registry_is_released():
    import manual_job_background as bg

    execution_id = "MBJ-TEST-RC1629"
    status = {
        "execution_id": execution_id, "state": "QUEUED", "phase": "START",
        "percent": 0, "cancel_requested": False, "lease_revoked": False,
    }
    stored = dict(status)

    def fake_get(_execution_id):
        return dict(stored)

    def fake_write(value):
        stored.clear()
        stored.update(dict(value))
        return dict(stored)

    bg._THREADS[execution_id] = object()
    with patch.object(bg, "get_status", side_effect=fake_get), \
         patch.object(bg, "_write_status", side_effect=fake_write), \
         patch.object(bg, "_write_progress_status", side_effect=fake_write), \
         patch("market_intelligence.run_job", side_effect=RuntimeError("canonical audit failed")):
        bg._worker(execution_id, {"name": "Test"}, "MANUAL", False)

    assert stored["state"] == "FAILED"
    assert stored["error"] == "canonical audit failed"
    assert stored.get("completed_at")
    assert execution_id not in bg._THREADS
