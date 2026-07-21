import json
import threading
from datetime import datetime, timezone
from pathlib import Path

import durable_runtime as dr
import investment_pipeline as ip
import market_intelligence as mi


def test_concurrent_local_mirror_writes_are_atomic(tmp_path):
    target = tmp_path / "runs" / "status.json"
    errors = []

    def writer(number):
        try:
            for sequence in range(25):
                dr._write_local(target, {"writer": number, "sequence": sequence})
        except Exception as exc:
            errors.append(exc)

    threads = [threading.Thread(target=writer, args=(n,)) for n in range(8)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    assert errors == []
    assert isinstance(json.loads(target.read_text(encoding="utf-8")), dict)
    assert list(target.parent.glob("*.tmp")) == []


def test_postgres_success_makes_local_mirror_best_effort(monkeypatch, tmp_path):
    class Storage:
        def write_json(self, key, value):
            return True

    monkeypatch.setattr(dr, "get_storage_service", lambda: Storage())
    monkeypatch.setattr(dr, "_write_local", lambda *args: (_ for _ in ()).throw(FileNotFoundError("mirror")))
    dr.write_json("status", tmp_path / "status.json", {"ok": True})


def test_report_filename_and_run_id_use_oslo_summer_time():
    created = "2026-07-21T07:45:33+00:00"
    run = {"created_at": created, "timezone_name": "Europe/Oslo", "job_name": "Morgenanalyse",
           "report_identity": {"type": "UTKAST", "label": "Utkast", "slug": "UTKAST"}}
    assert "20260721T094533" in mi.safe_report_filename(run, "pdf")
    assert mi.local_run_id("MI", created, "Europe/Oslo") == "MI-20260721-094533"


def test_archive_entry_contains_local_time():
    entry = mi._archive_entry({"run_id": "MI-1", "created_at": "2026-07-21T07:45:33+00:00",
                               "timezone_name": "Europe/Oslo", "candidates": [], "summary": {},
                               "markets": [], "job_name": "Test", "report_identity": {"type": "UTKAST", "label": "Utkast"}})
    assert entry["created_at_local"].startswith("21.07.2026 09:45:33")


def test_full_analysis_respects_intelligence_source_cache(monkeypatch):
    captured = {}
    monkeypatch.delenv("STRICT_INTELLIGENCE_SOURCE_REFRESH", raising=False)
    monkeypatch.setattr(ip, "_prepare_candidate_rows", lambda rows, cfg, progress_callback, force_refresh: [])
    result = ip.run_pipeline([], ip.PipelineConfig(), force_refresh=True)
    assert result["data_refresh"]["force_refresh"] is True
    assert result["data_refresh"]["intelligence_source_cache_respected"] is True


def test_ui_has_one_shot_terminal_full_refresh():
    source = Path("autonomous_orchestrator_ui.py").read_text(encoding="utf-8")
    assert "orchestrator_terminal_app_refresh_v18712" in source
    assert 'st.rerun(scope="app")' in source
