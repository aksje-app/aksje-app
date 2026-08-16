from __future__ import annotations

import subprocess

import autonomous_portfolio as autonomy
import manual_job_background as background


def test_parallel_strategy_timeout_is_killable_and_bounded(monkeypatch):
    def expire(*args, **kwargs):
        assert kwargs["timeout"] == 5
        raise subprocess.TimeoutExpired(args[0], kwargs["timeout"])

    monkeypatch.setattr(autonomy.subprocess, "run", expire)

    try:
        autonomy._evaluate_parallel_strategies_isolated(
            {"snapshot_id": "SNAP-RC1631R", "candidates": []},
            run_id="RUN-RC1631R",
            autonomy_portfolio={},
            technical_portfolio={},
            params=autonomy.AutonomousParameters(),
            timeout_seconds=1,
        )
    except autonomy.ParallelStrategyTimeout as exc:
        assert "5 sekunder" in str(exc)
    else:
        raise AssertionError("Forventet kontrollert timeout")


def test_stalled_watchdog_does_not_claim_worker_or_report_lock_released(monkeypatch):
    monkeypatch.setattr(background, "_thread_is_alive", lambda execution_id: True)
    monkeypatch.setattr(background, "_write_status", lambda status: dict(status))
    status = {
        "execution_id": "MBJ-RC1631R-STALLED",
        "state": "RUNNING",
        "active_stage": "AUTONOMOUS",
        "last_progress_at": "2020-01-01T00:00:00+00:00",
    }

    reconciled = background.reconcile_orphaned_status(status)

    assert reconciled["state"] == "STALLED"
    assert reconciled["publication_lease_revoked"] is True
    assert reconciled["worker_terminated"] is False
    assert reconciled["report_lock_released"] is False
    assert "frigitt" not in reconciled["message"].lower()


def test_manual_release_only_revokes_publication_lease(monkeypatch):
    status = {
        "execution_id": "MBJ-RC1631R-MANUAL",
        "state": "RUNNING",
        "active_stage": "AUTONOMOUS",
    }
    monkeypatch.setattr(background, "get_status", lambda execution_id: dict(status))
    monkeypatch.setattr(background, "_write_status", lambda value: dict(value))

    released = background.force_release(status["execution_id"], requested_by="TEST")

    assert released["lease_revoked"] is True
    assert released["worker_terminated"] is False
    assert released["report_lock_released"] is False
    assert "ny kjøring kan startes" not in released["message"].lower()


def test_isolated_worker_is_shipped_next_to_parent_module():
    worker = autonomy.Path(autonomy.__file__).with_name("parallel_strategy_isolated_worker.py")
    assert worker.is_file()
    source = worker.read_text(encoding="utf-8")
    assert "evaluate_snapshot" in source
    assert "execution_authorized" not in source
