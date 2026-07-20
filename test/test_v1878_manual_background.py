import threading
import time

import manual_job_background as background
import market_intelligence as mi


def _memory_storage(monkeypatch):
    memory = {}

    def write_json(key, path, value):
        memory[key] = dict(value)

    def read_json(key, path, default):
        value = memory.get(key, default)
        return dict(value) if isinstance(value, dict) else value

    monkeypatch.setattr(background, "write_json", write_json)
    monkeypatch.setattr(background, "read_json", read_json)
    background._THREADS.clear()
    return memory


def test_manual_job_returns_immediately_and_finishes_without_ui_thread(monkeypatch):
    _memory_storage(monkeypatch)
    release = threading.Event()

    def fake_run_job(job, trigger, progress_callback, force_refresh):
        progress_callback({"phase": "MARKET_DATA", "completed": 1, "total": 2, "message": "Henter data"})
        release.wait(timeout=2)
        return {
            "run_id": "MI-1",
            "candidates": [{"ticker": "TEST", "investment_score": 80}],
            "autonomous_chain": {"chain_id": "AO-1", "status": "OK", "stages": []},
        }

    monkeypatch.setattr(mi, "run_job", fake_run_job)
    job = mi.JobProfile(name="Bakgrunnstest")
    started = time.perf_counter()
    accepted = background.start_manual_job(job, trigger="MANUAL_DRAFT_TEST")
    assert time.perf_counter() - started < 0.2
    assert accepted["state"] == "QUEUED"

    deadline = time.time() + 1
    while background.get_active_status().get("state") != "RUNNING" and time.time() < deadline:
        time.sleep(0.01)
    assert background.is_running(background.get_active_status())

    release.set()
    for thread in list(background._THREADS.values()):
        thread.join(timeout=2)
    final = background.get_active_status()
    assert final["state"] == "COMPLETED"
    assert final["chain_id"] == "AO-1"
    assert final["percent"] == 100


def test_second_click_does_not_start_duplicate_running_job(monkeypatch):
    _memory_storage(monkeypatch)
    release = threading.Event()
    calls = []

    def fake_run_job(*args, **kwargs):
        calls.append(1)
        release.wait(timeout=2)
        return {"run_id": "MI-1", "autonomous_chain": {"chain_id": "AO-1", "status": "OK"}}

    monkeypatch.setattr(mi, "run_job", fake_run_job)
    job = mi.JobProfile(name="Duplikatvern")
    first = background.start_manual_job(job, trigger="MANUAL_FULL_CHAIN")
    second = background.start_manual_job(job, trigger="MANUAL_FULL_CHAIN")
    assert second["execution_id"] == first["execution_id"]
    release.set()
    for thread in list(background._THREADS.values()):
        thread.join(timeout=2)
    assert len(calls) == 1


def test_progress_percent_is_bounded_and_monotonic_inside_phase():
    assert background.progress_percent({"phase": "MARKET_DATA", "completed": 0, "total": 10}) == 10
    assert background.progress_percent({"phase": "MARKET_DATA", "completed": 5, "total": 10}) > 10
    assert background.progress_percent({"phase": "COMPLETE", "completed": 1, "total": 1}) == 100
