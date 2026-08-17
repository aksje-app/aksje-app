from __future__ import annotations

import json

import autonomous_portfolio as autonomy
import execution_coordination as coordination
import manual_job_background as background
from repositories.application import RepositoryRegistry
from services.market_snapshot_service import MarketSnapshotService
from services.storage_service import StorageService


def _service(tmp_path) -> MarketSnapshotService:
    storage = StorageService(base_dir=tmp_path, database_url="", mode="local")
    return MarketSnapshotService(RepositoryRegistry(storage))


def test_sixty_large_candidates_are_bounded_and_report_batch_progress(tmp_path):
    service = _service(tmp_path)
    huge_article = "x" * 250_000
    candidates = [
        {
            "ticker": f"T{index:02d}", "price": 100.0 + index, "score": 70.0,
            "risk_score": 30.0, "data_quality": 95.0,
            "raw": {"provider": {"body": huge_article}},
            "articles": [{"body": huge_article} for _ in range(4)],
            "decision_evidence": {"summary": "y" * 150_000},
        }
        for index in range(60)
    ]
    progress = []
    snapshot = service.build_market_snapshot(
        candidates, run_id="STRESS-60-67", source="stress",
        progress_callback=lambda completed, total, ticker: progress.append((completed, total, ticker)),
    ).to_dict()

    encoded = json.dumps(snapshot, ensure_ascii=False).encode("utf-8")
    assert len(snapshot["candidates"]) == 60
    assert len(encoded) < 6 * 1024 * 1024
    assert [row[0] for row in progress] == [10, 20, 30, 40, 50, 60]
    for row in snapshot["candidates"]:
        inputs = row["decision_inputs"]
        assert "raw" not in inputs
        assert "articles" not in inputs
        assert len(json.dumps(inputs, ensure_ascii=False).encode("utf-8")) < 100 * 1024


def test_restart_releases_matching_orphaned_execution_owner(monkeypatch):
    state = {
        "state": "ACTIVE", "execution_id": "MBJ-RESOURCE", "process_identity": "40:old",
    }
    monkeypatch.setattr(coordination, "report_execution_owner", lambda: dict(state))
    monkeypatch.setattr(coordination, "write_json", lambda key, path, value: state.update(value))
    released = coordination.release_orphaned_execution_owner(
        reason="PROBABLE_RESOURCE_RESTART", execution_id="MBJ-RESOURCE",
    )
    assert released["state"] == "RELEASED_AFTER_PROCESS_RESTART"
    assert released["release_reason"] == "PROBABLE_RESOURCE_RESTART"


def test_sixty_candidates_and_sixty_seven_learning_positions_are_bounded(tmp_path):
    service = _service(tmp_path)
    candidates = {
        f"T{index:02d}": {"ticker": f"T{index:02d}", "price": 100.0, "score": 70.0}
        for index in range(60)
    }
    snapshot = service.build_market_snapshot(list(candidates.values()), run_id="STRESS-60-67")
    portfolio = {
        "positions": {
            f"T{index:02d}": {
                "ticker": f"T{index:02d}", "quantity": 1.0,
                "average_price": 100.0, "last_price": 100.0,
                "highest_price": 100.0, "opened_at": background._now(),
            }
            for index in range(67)
        }
    }
    params = autonomy.AutonomousParameters(
        stop_loss_pct=99.0, trailing_stop_pct=99.0,
        take_profit_pct=999.0, score_exit_threshold=0.0,
        learning_probe_horizon_days=60,
    )
    decisions, trades = autonomy._update_learning_positions(
        portfolio, candidates, "STRESS-60-67", params,
    )
    assert len(snapshot.candidates) == 60
    assert len(decisions) == 67
    assert trades == []
    assert len(portfolio["positions"]) == 67


def test_fresh_autonomy_heartbeat_classifies_probable_resource_restart(monkeypatch):
    monkeypatch.setattr(background, "_PROCESS_IDENTITY", "99:new")
    monkeypatch.setattr(background, "_write_status", lambda value: dict(value))
    status = {
        "execution_id": "MBJ-RESOURCE", "state": "RUNNING", "active_stage": "AUTONOMOUS",
        "worker_process_identity": "40:old", "heartbeat_at": background._now(),
    }
    reconciled = background.reconcile_orphaned_status(status)
    assert reconciled["state"] == "CANCELLED"
    assert reconciled["restart_classification"] == "PROBABLE_RESOURCE_RESTART"
    assert reconciled["restart_evidence"]["heartbeat_was_fresh"] is True
