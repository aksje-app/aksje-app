from __future__ import annotations

import io
import zipfile
from unittest.mock import patch

from app_version import APP_VERSION
from learning_acceptance import evaluate_learning_run
from market_intelligence import CORE_MARKET_SCOPE_LABEL, JobProfile
from report_test_mode import build_test_job


def test_version_and_new_job_defaults_are_bounded_core_markets():
    assert APP_VERSION == "v19.22.0-rc16.31"
    job = JobProfile(name="Ny fast jobb")
    assert job.markets == [CORE_MARKET_SCOPE_LABEL]
    assert job.scan_limit == 25
    assert job.deep_count == 10
    assert job.evidence_analysis_count == 10


def test_saved_job_parameters_are_not_silently_replaced():
    saved = JobProfile.from_dict({
        "name": "Redigerbar fast rapport", "markets": ["Norge"],
        "market_profile": "CUSTOM", "schedules": ["22:00"],
        "scan_limit": 35, "deep_count": 7, "evidence_analysis_count": 6,
    })
    assert saved.scan_limit == 35
    assert saved.deep_count == 7
    assert saved.evidence_analysis_count == 6
    assert saved.markets == ["Norge"]


def test_acceptance_report_test_runs_real_isolated_learning_chain():
    source = JobProfile(name="Fast", markets=["Norge"], schedules=["08:00"])
    with patch("market_intelligence.load_jobs", return_value=[source]):
        test_job = build_test_job()
    assert test_job.markets == [CORE_MARKET_SCOPE_LABEL]
    assert test_job.schedules == []
    assert test_job.scan_limit == 25
    assert test_job.run_autonomous_portfolio is True
    assert test_job.run_controlled_learning is True
    assert test_job.require_active_portfolio is False


def test_learning_acceptance_pass_requires_persisted_theoretical_observation(tmp_path):
    run = {
        "run_id": "MI-TEST-1", "report_id": "MI-TEST-1", "trigger": "SCHEDULED_REPORT_TEST_NOTIFICATION",
        "candidates": [{"ticker": "TEST.OL"}],
        "autonomous_chain": {
            "status": "OK",
            "learning_portfolio": {"last_run_id": "MI-TEST-1", "positions": {"TEST.OL": {"ticker": "TEST.OL"}}},
            "learning_decisions": [{"ticker": "TEST.OL", "action": "ADD_OBSERVATION", "reason": "Læringskjøp", "score": 64}],
            "learning_trades": [{"trade_id": "LT-1", "ticker": "TEST.OL", "action": "BUY", "mode": "LEARNING_ONLY"}],
            "learning_performance": {"observation_count": 1},
        },
    }
    with patch("learning_acceptance.write_json"):
        result = evaluate_learning_run(run)
    assert result["verdict"] == "PASS"
    assert result["checks"]["production_trade_separation"] is True
    assert result["decision_trace"][0]["first_blocker_code"] == "NONE"


def test_learning_acceptance_partial_has_concrete_blocker():
    run = {
        "run_id": "MI-TEST-2", "report_id": "MI-TEST-2", "candidates": [{"ticker": "WAIT.OL"}],
        "autonomous_chain": {
            "status": "OK", "learning_portfolio": {"last_run_id": "MI-TEST-2", "positions": {}},
            "learning_decisions": [{"ticker": "WAIT.OL", "action": "OBSERVE", "reason": "Under læringsgrense 59.0 < 63.0"}],
            "learning_trades": [], "learning_performance": {},
        },
    }
    with patch("learning_acceptance.write_json"):
        result = evaluate_learning_run(run)
    assert result["verdict"] == "PARTIAL"
    assert result["decision_trace"][0]["first_blocker_code"] == "LEARNING_SCORE_BELOW_THRESHOLD"


def test_diagnostic_bundle_contains_learning_and_checksums():
    import manual_job_background as bg
    with patch.object(bg, "get_status", return_value={"execution_id": "E-1", "state": "COMPLETED"}), \
         patch("learning_acceptance.build_learning_diagnostics", return_value={"acceptance": {"verdict": "PASS"}}), \
         patch("report_test_mode.load_report_test_mode", return_value={"enabled": False}), \
         patch("scheduled_runner.load_unattended_state", return_value={"state": "COMPLETED"}):
        payload, _ = bg.diagnostic_bundle("E-1")
    with zipfile.ZipFile(io.BytesIO(payload)) as archive:
        names = set(archive.namelist())
        assert "learning/LEARNING_DIAGNOSTICS.json" in names
        assert "learning/LEARNING_ACCEPTANCE.json" in names
        assert "scheduler/SCHEDULER_STATUS.json" in names
        assert "SHA256SUMS" in names
