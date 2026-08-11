from __future__ import annotations

import json
from pathlib import Path

import manual_job_background as jobs


def _reset_snapshot(monkeypatch) -> None:
    monkeypatch.setattr(jobs, "_LATEST_ACTIVE_SNAPSHOT", {})


def test_poll_snapshot_reads_process_memory_without_durable_storage(monkeypatch):
    _reset_snapshot(monkeypatch)
    jobs._publish_runtime_snapshot({
        "execution_id": "MBJ-POLL-1", "state": "RUNNING", "percent": 42,
        "updated_at": "2026-08-05T17:20:00+00:00",
    })
    monkeypatch.setattr(jobs, "read_json", lambda *_a, **_k: (_ for _ in ()).throw(AssertionError("durable read")))
    value = jobs.get_active_status_snapshot()
    assert value["execution_id"] == "MBJ-POLL-1"
    assert value["percent"] == 42
    assert value["ui_poll_source"] == "PROCESS_MEMORY"


def test_poll_snapshot_observes_successive_worker_updates(monkeypatch):
    _reset_snapshot(monkeypatch)
    jobs._publish_runtime_snapshot({"execution_id": "MBJ-POLL-2", "state": "RUNNING", "percent": 5})
    assert jobs.get_active_status_snapshot()["percent"] == 5
    jobs._publish_runtime_snapshot({"execution_id": "MBJ-POLL-2", "state": "RUNNING", "percent": 72})
    assert jobs.get_active_status_snapshot()["percent"] == 72
    jobs._publish_runtime_snapshot({"execution_id": "MBJ-POLL-2", "state": "COMPLETED", "percent": 100})
    assert jobs.get_active_status_snapshot()["state"] == "COMPLETED"


def test_poll_snapshot_uses_atomic_local_mirror_before_database(monkeypatch, tmp_path):
    _reset_snapshot(monkeypatch)
    root = tmp_path / "manual_background_jobs"
    active_path = root / "active.json"
    run_path = root / "runs" / "MBJ-LOCAL.json"
    run_path.parent.mkdir(parents=True)
    active_path.write_text(json.dumps({"execution_id": "MBJ-LOCAL"}), encoding="utf-8")
    run_path.write_text(json.dumps({"execution_id": "MBJ-LOCAL", "state": "RUNNING", "percent": 61}), encoding="utf-8")
    monkeypatch.setattr(jobs, "ROOT", root)
    monkeypatch.setattr(jobs, "ACTIVE_PATH", active_path)
    monkeypatch.setattr(jobs, "get_active_status", lambda: (_ for _ in ()).throw(AssertionError("database fallback")))
    value = jobs.get_active_status_snapshot()
    assert value["percent"] == 61
    assert value["ui_poll_source"] == "LOCAL_ATOMIC_MIRROR"


def test_status_publish_happens_before_slow_durable_write(monkeypatch, tmp_path):
    _reset_snapshot(monkeypatch)
    monkeypatch.setattr(jobs, "ROOT", tmp_path)
    monkeypatch.setattr(jobs, "ACTIVE_PATH", tmp_path / "active.json")
    observed = []

    def fake_write(*_args, **_kwargs):
        observed.append(jobs.get_active_status_snapshot().get("percent"))

    monkeypatch.setattr(jobs, "write_json", fake_write)
    jobs._write_status({"execution_id": "MBJ-WRITE", "state": "RUNNING", "percent": 33})
    assert observed == [33, 33]


def test_report_center_reuses_overview_progress_fragment():
    source = Path("market_intelligence.py").read_text(encoding="utf-8")
    render_section = source[source.index("def render_market_intelligence"):]
    action = render_section[render_section.index("##### 2. Handlinger"):render_section.index("##### 3. Siste rapporter")]
    assert "from autonomy_overview import render_shared_manual_job_progress" in action
    assert "render_shared_manual_job_progress(" in action
    assert "refresh_app_on_terminal=False" in action
    assert "_live_report_progress_fragment_v19220_rc161()" not in action

    overview = Path("autonomy_overview.py").read_text(encoding="utf-8")
    shared = overview[overview.index("def _live_progress_panel"):overview.index("def render_autonomy_overview")]
    assert 'fragment(run_every="5s")(_live_progress_panel)' in shared
    assert "get_active_status()" in shared
    assert "render_shared_manual_job_progress" in shared


def test_hotfix_scope_does_not_touch_report_or_trading_engines():
    version = Path("app_version.py").read_text(encoding="utf-8")
    assert 'APP_VERSION = "v19.22.0-rc16.7"' in version
    assert "Ingen endring i rapportmotor, score, beslutningsregler, scheduler, porteføljer eller handel" in version
