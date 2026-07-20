import json
import time
from pathlib import Path

import durable_runtime as durable
import market_intelligence as mi
import autonomous_portfolio as portfolio


class FakeStorage:
    def __init__(self):
        self.json = {}
        self.events = {}

    def read_json(self, name, default=None):
        return self.json.get(name, default)

    def write_json(self, name, value):
        self.json[name] = json.loads(json.dumps(value, default=str))
        return True

    def append_jsonl(self, name, row):
        self.events.setdefault(name, []).append(dict(row))
        return True

    def read_jsonl(self, name, limit=500):
        return self.events.get(name, [])[-limit:]


def test_json_rehydrates_after_local_runtime_loss(tmp_path, monkeypatch):
    storage = FakeStorage()
    monkeypatch.setattr(durable, "get_storage_service", lambda: storage)
    path = tmp_path / "runtime" / "trades.json"
    durable.write_json("autonomous_portfolio/trades.json", path, [{"trade_id": "T1"}])
    path.unlink()

    assert durable.read_json("autonomous_portfolio/trades.json", path, []) == [{"trade_id": "T1"}]
    assert json.loads(path.read_text(encoding="utf-8"))[0]["trade_id"] == "T1"


def test_jsonl_rehydrates_after_local_runtime_loss(tmp_path, monkeypatch):
    storage = FakeStorage()
    monkeypatch.setattr(durable, "get_storage_service", lambda: storage)
    path = tmp_path / "runtime" / "audit.jsonl"
    durable.append_event("autonomous_portfolio/audit.jsonl", path, {"event": "BUY"})
    path.unlink()

    assert durable.read_events("autonomous_portfolio/audit.jsonl", path) == [{"event": "BUY"}]
    assert "BUY" in path.read_text(encoding="utf-8")


def test_report_archive_uses_durable_reader(monkeypatch):
    expected = [{"run_id": "MI-PERSISTED", "report_type": "MORGENRAPPORT"}]
    monkeypatch.setattr(mi, "durable_read_json", lambda key, path, default: expected if key == "market_intelligence/report_archive.json" else default)
    assert mi._load_report_archive() == expected


def test_report_archive_migrates_configuration_framework_copy(monkeypatch):
    legacy = [{"run_id": "MI-LEGACY", "report_type": "MORGENRAPPORT"}]
    written = []
    monkeypatch.setattr(mi, "_read", lambda path, default: [])
    monkeypatch.setattr(mi, "read_persistent_json", lambda key, default=None: legacy)
    monkeypatch.setattr(mi, "_write", lambda path, value: written.extend(value))
    monkeypatch.setattr(mi, "_audit", lambda *args, **kwargs: None)
    assert mi._load_report_archive() == legacy
    assert written == legacy


def test_duplicate_job_names_keep_active_profile(monkeypatch):
    rows = [
        {"job_id": "OLD", "name": "Morgenanalyse", "enabled": False, "last_run_at": "2026-07-20T08:00:00+00:00"},
        {"job_id": "ACTIVE", "name": "Morgenanalyse", "enabled": True, "last_run_at": "2026-07-20T09:00:00+00:00"},
    ]
    saved = []
    monkeypatch.setattr(mi, "read_persistent_json", lambda key, default=None: rows)
    monkeypatch.setattr(mi, "save_jobs", lambda jobs: saved.extend(jobs))
    monkeypatch.setattr(mi, "_audit", lambda *args, **kwargs: None)
    jobs = mi.load_jobs()
    assert [job.job_id for job in jobs] == ["ACTIVE"]
    assert [job.job_id for job in saved] == ["ACTIVE"]


def test_background_scheduler_returns_without_waiting(monkeypatch):
    import scheduler_background as scheduler
    monkeypatch.setattr(mi, "run_due_jobs", lambda: (time.sleep(0.25), [1])[1])
    scheduler._THREAD = None
    started = time.perf_counter()
    status = scheduler.kick_scheduler_background()
    elapsed = time.perf_counter() - started
    assert elapsed < 0.1
    assert status["state"] == "RUNNING"
    scheduler._THREAD.join(timeout=1)
    assert scheduler.scheduler_status()["runs"] == 1


def test_open_positions_get_transparent_recovered_trade_rows(monkeypatch):
    memory = {portfolio.TRADES_PATH: [], portfolio.DECISIONS_PATH: []}
    monkeypatch.setattr(portfolio, "_read", lambda path, default: memory.get(path, default))
    monkeypatch.setattr(portfolio, "_write", lambda path, value: memory.__setitem__(path, value))
    monkeypatch.setattr(portfolio, "_append_audit", lambda *args, **kwargs: None)
    state = {"positions": {"GOOG": {"quantity": 2, "average_price": 100, "opened_at": "2026-07-19T10:00:00+00:00", "source_run_id": "MI-OLD"}}}
    assert portfolio.recover_missing_position_history(state) == 1
    assert memory[portfolio.TRADES_PATH][0]["recovered"] is True
    assert memory[portfolio.TRADES_PATH][0]["value"] == 200
    assert memory[portfolio.DECISIONS_PATH][0]["action"] == "RECOVERED"
