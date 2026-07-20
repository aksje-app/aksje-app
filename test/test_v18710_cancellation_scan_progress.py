import json
import threading
import time
from pathlib import Path

import manual_job_background as background
import market_intelligence as mi
from execution_control import ExecutionCancelled


def _memory_storage(monkeypatch):
    memory = {}

    def write_json(key, path, value):
        memory[key] = json.loads(json.dumps(value, default=str))

    def read_json(key, path, default):
        return json.loads(json.dumps(memory.get(key, default)))

    monkeypatch.setattr(background, "write_json", write_json)
    monkeypatch.setattr(background, "read_json", read_json)
    background._THREADS.clear()
    return memory


def test_cancel_request_stops_worker_at_safe_checkpoint(monkeypatch):
    _memory_storage(monkeypatch)
    checkpoint = threading.Event()
    continue_work = threading.Event()
    published = []

    def fake_run_job(job, trigger, progress_callback, force_refresh):
        progress_callback({"phase": "MARKET_DATA", "completed": 1, "total": 10, "message": "Data"})
        checkpoint.set()
        continue_work.wait(timeout=2)
        progress_callback({"phase": "MARKET_DATA", "completed": 2, "total": 10, "message": "Data"})
        published.append(True)
        return {"run_id": "SHOULD-NOT-PUBLISH", "autonomous_chain": {"status": "OK"}}

    monkeypatch.setattr(mi, "run_job", fake_run_job)
    job = mi.JobProfile(name="Stopp-test", scan_limit=250, markets=["Alle"])
    accepted = background.start_manual_job(job, trigger="MANUAL_DRAFT_TEST")
    assert checkpoint.wait(timeout=1)
    stopped = background.request_cancel(accepted["execution_id"], requested_by="TEST")
    assert stopped["state"] == "STOP_REQUESTED"
    continue_work.set()
    for thread in list(background._THREADS.values()):
        thread.join(timeout=2)
    final = background.get_active_status()
    assert final["state"] == "CANCELLED"
    assert final["partial_results_published"] is False
    assert published == []


def test_started_status_records_actual_scan_limit_and_total(monkeypatch):
    _memory_storage(monkeypatch)
    release = threading.Event()

    def fake_run_job(*args, **kwargs):
        release.wait(timeout=2)
        return {"run_id": "MI-1", "autonomous_chain": {"chain_id": "AO-1", "status": "OK"}}

    monkeypatch.setattr(mi, "run_job", fake_run_job)
    status = background.start_manual_job(mi.JobProfile(name="Maks", scan_limit=250, markets=["Alle"]), trigger="MANUAL_FULL_CHAIN")
    assert status["scan_configuration"]["per_market"] == 250
    assert status["scan_configuration"]["planned_maximum"] == 1500
    release.set()
    for thread in list(background._THREADS.values()):
        thread.join(timeout=2)


def test_progress_is_monotonic_across_markets_and_knows_insider_news():
    first_market_end = background.progress_percent({"phase": "SCORING", "completed": 10, "total": 10, "market_index": 1, "market_total": 2})
    second_market_start = background.progress_percent({"phase": "MARKET_DATA", "completed": 0, "total": 10, "market_index": 2, "market_total": 2})
    insider = background.progress_percent({"phase": "INSIDER", "completed": 5, "total": 10, "market_index": 2, "market_total": 2})
    news = background.progress_percent({"phase": "NEWS", "completed": 5, "total": 10, "market_index": 2, "market_total": 2})
    assert second_market_start >= first_market_end
    assert news > insider > 5


def test_scan_profile_menu_has_explicit_maximum():
    assert mi.SCAN_PROFILES["Maks (250)"] == 250
    assert mi.SCAN_PROFILES["Standard (20)"] == 20
    assert mi.SCAN_PROFILES["Egendefinert (10–250)"] is None


def test_ui_contains_stage_boxes_and_cancel_control():
    source = Path("autonomous_orchestrator_ui.py").read_text(encoding="utf-8")
    assert "Stopp pågående kjøring" in source
    assert "completed_steps" in source
    assert "st.success" in source


def test_run_job_does_not_convert_cancel_into_market_error(monkeypatch):
    monkeypatch.setattr(mi, "_effective_execution_job", lambda job, trigger: (job, {}))
    monkeypatch.setattr(mi, "_recent_validated_draft", lambda *args, **kwargs: None)
    monkeypatch.setattr(mi, "_read", lambda *args, **kwargs: {})
    monkeypatch.setattr(mi, "normalize_markets", lambda markets: ["Norge"])
    monkeypatch.setattr(mi, "_load_candidate_rows_from_app", lambda cfg: ([{"ticker": "TEST.OL"}], "test"))
    monkeypatch.setattr(mi, "run_pipeline", lambda *args, **kwargs: (_ for _ in ()).throw(ExecutionCancelled("stopp")))
    try:
        mi.run_job(mi.JobProfile(name="Avbryt"), trigger="MANUAL_DRAFT_TEST")
    except ExecutionCancelled:
        pass
    else:
        raise AssertionError("ExecutionCancelled ble feilaktig konvertert til en markedsfeil")
