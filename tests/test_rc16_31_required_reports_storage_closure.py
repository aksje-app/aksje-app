from __future__ import annotations

from datetime import datetime, timezone
import json

import market_intelligence as mi
import cron_control
import paper_scanner_runtime
from autonomi_core.learning_reporting import layer
from services.storage_service import StorageService
from report_test_mode import build_test_job


def test_immutable_local_store_creates_once_and_returns_existing(tmp_path):
    storage = StorageService(base_dir=tmp_path, mode="local", allow_local_fallback=True)
    first = {"result_id": "R1", "content_hash": "A"}
    assert storage.write_json_immutable("results/R1.json", first) == first
    assert storage.write_json_immutable("results/R1.json", {"result_id": "R1", "content_hash": "B"}) == first


def test_immutable_postgres_transaction_retries_transient_connection_failure(monkeypatch, tmp_path):
    storage = StorageService(base_dir=tmp_path, database_url="postgresql://example.invalid/db", mode="postgres", allow_local_fallback=False)
    payload = {"result_id": "R-RETRY", "content_hash": "HASH"}
    calls = {"connections": 0}

    class Cursor:
        def execute(self, *args, **kwargs):
            return None
        def fetchone(self):
            return (json.dumps(payload),)

    class Connection:
        def cursor(self): return Cursor()
        def commit(self): return None
        def rollback(self): return None
        def close(self): return None

    monkeypatch.setattr(storage, "using_postgres", lambda: True)
    monkeypatch.setattr(storage, "init_db", lambda: True)
    def connect():
        calls["connections"] += 1
        if calls["connections"] < 3:
            raise OSError("temporary database outage")
        return Connection()
    monkeypatch.setattr(storage, "_conn", connect)
    assert storage.write_json_immutable("results/R-RETRY.json", payload, attempts=3) == payload
    assert calls["connections"] == 3


def test_canonical_index_outage_does_not_invalidate_stored_result(monkeypatch):
    run = {"run_id": "MI-IMMUTABLE-1", "candidates": [], "summary": {}}
    expected = layer.build_canonical_result(run)
    monkeypatch.setattr(layer, "write_immutable_json", lambda *args, **kwargs: expected)
    monkeypatch.setattr(layer, "read_json", lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError("index unavailable")))
    stored = layer.save_canonical_result(run)
    assert stored["result_id"] == "RESULT-MI-IMMUTABLE-1"


def test_three_required_reports_are_created_with_stable_oslo_schedules():
    jobs, changes = mi.ensure_required_report_jobs([])
    assert [(job.job_id, job.schedules, job.timezone_name, job.enabled) for job in jobs] == [
        ("MI-REQUIRED-MORNING", ["08:00"], "Europe/Oslo", True),
        ("MI-REQUIRED-AFTERNOON", ["14:00"], "Europe/Oslo", True),
        ("MI-REQUIRED-EVENING", ["22:00"], "Europe/Oslo", True),
    ]
    assert len(changes) == 3


def test_required_report_repair_preserves_analysis_budget():
    source = mi.JobProfile(
        job_id="OLD", name="Morgenrapport", schedules=[], enabled=False,
        scan_limit=100, deep_count=20, evidence_analysis_count=15,
    )
    jobs, _ = mi.ensure_required_report_jobs([source])
    morning = next(job for job in jobs if job.job_id == "MI-REQUIRED-MORNING")
    assert morning.scan_limit == 100
    assert morning.deep_count == 20
    assert morning.evidence_analysis_count == 15
    assert morning.schedules == ["08:00"] and morning.enabled is True


def test_daily_ledger_tracks_all_three_deliveries(monkeypatch):
    jobs, _ = mi.ensure_required_report_jobs([])
    monkeypatch.setattr(mi, "load_jobs", lambda: jobs)
    history = []
    for job, planned in zip(jobs, ("06:00", "12:00", "20:00")):
        history.append({
            "job_id": job.job_id, "planned_at": f"2026-08-11T{planned}:00+00:00",
            "status": "Fullført", "pdf": True, "pushover_sent": True, "run_id": f"RUN-{job.job_id}",
        })
    monkeypatch.setattr(mi, "load_job_history", lambda limit=2000: history)
    ledger = mi.required_report_delivery_ledger(datetime(2026, 8, 11, 21, 0, tzinfo=timezone.utc))
    assert ledger["complete"] is True
    assert [row["status"] for row in ledger["rows"]] == ["SENDT", "SENDT", "SENDT"]


def test_all_three_due_jobs_are_attempted_even_when_middle_one_fails(monkeypatch):
    jobs, _ = mi.ensure_required_report_jobs([])
    attempted = []
    monkeypatch.setattr(mi, "load_jobs", lambda: jobs)
    monkeypatch.setattr(mi, "_due_slot_info", lambda *args, **kwargs: {"due": True, "previous_planned_utc": "2026-08-11T06:00:00+00:00"})
    monkeypatch.setattr(mi, "upsert_job", lambda job: None)
    monkeypatch.setattr(mi, "_append_job_history", lambda row: None)
    monkeypatch.setattr(mi, "_audit", lambda *args, **kwargs: None)
    monkeypatch.setattr(mi, "scheduler_health_snapshot", lambda *args, **kwargs: {})

    def run(job, **kwargs):
        attempted.append(job.job_id)
        if job.job_id == "MI-REQUIRED-AFTERNOON":
            raise RuntimeError("injected storage outage")
        return {"run_id": "RUN-" + job.job_id}

    monkeypatch.setattr(mi, "run_job", run)
    results = mi.run_due_jobs(authoritative_unattended=True)
    assert attempted == [job.job_id for job in jobs]
    assert len(results) == 3
    assert sum(row.get("scheduler_result") == "FAILED" for row in results) == 1


def test_morning_afternoon_evening_run_in_chronological_slots(monkeypatch):
    jobs, _ = mi.ensure_required_report_jobs([])
    attempted = []
    monkeypatch.setattr(mi, "load_jobs", lambda: jobs)
    monkeypatch.setattr(mi, "upsert_job", lambda job: None)
    monkeypatch.setattr(mi, "_append_job_history", lambda row: None)
    monkeypatch.setattr(mi, "_audit", lambda *args, **kwargs: None)
    monkeypatch.setattr(mi, "scheduler_health_snapshot", lambda *args, **kwargs: {})
    monkeypatch.setattr(mi, "run_job", lambda job, **kwargs: attempted.append(job.job_id) or {"run_id": "RUN-" + job.job_id})

    active_schedule = {"value": "08:00"}
    monkeypatch.setattr(mi, "_due_slot_info", lambda job, *args, **kwargs: {
        "due": job.schedules == [active_schedule["value"]],
        "previous_planned_utc": "2026-08-11T00:00:00+00:00",
    })
    for schedule, hour in (("08:00", 6), ("14:00", 12), ("22:00", 20)):
        active_schedule["value"] = schedule
        mi.run_due_jobs(datetime(2026, 8, 11, hour, 0, tzinfo=timezone.utc), authoritative_unattended=True)
    assert attempted == [
        "MI-REQUIRED-MORNING", "MI-REQUIRED-AFTERNOON", "MI-REQUIRED-EVENING",
    ]


def test_delivery_retry_uses_stored_run_without_new_analysis(monkeypatch):
    jobs, _ = mi.ensure_required_report_jobs([])
    morning = jobs[0]
    monkeypatch.setattr(mi, "load_jobs", lambda: jobs)
    monkeypatch.setattr(mi, "load_job_history", lambda limit=500: [{
        "job_id": morning.job_id, "job_name": morning.name, "run_id": "RUN-STORED",
        "planned_at": "2026-08-11T06:00:00+00:00", "pdf": True,
        "pushover_sent": False,
    }])
    monkeypatch.setattr(mi, "load_run", lambda run_id: {
        "run_id": run_id, "created_at": "2026-08-11T06:05:00+00:00",
        "persistence": {"ok": True},
        "pdf_delivery": {"generated": True, "validated": True, "published": True},
        "notification": {"sent": False},
    })
    monkeypatch.setattr(mi, "_notification", lambda job, run: (True, "Sendt på nytt"))
    monkeypatch.setattr(mi, "_write", lambda *args, **kwargs: None)
    history = []
    monkeypatch.setattr(mi, "_append_job_history", history.append)
    # A new analysis would require run_job; make accidental use fail loudly.
    monkeypatch.setattr(mi, "run_job", lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("analysis restarted")))
    result = mi.retry_pending_required_report_deliveries()
    assert result["sent"] == 1
    assert history[0]["type"] == "Leveringsretry"


def test_legacy_1630_schedule_migrates_to_1400():
    assert mi.normalize_schedule_value("16:30") == "14:00"


def test_required_jobs_disable_known_legacy_duplicates_but_preserve_custom_jobs():
    required, _ = mi.ensure_required_report_jobs([])
    legacy = mi.JobProfile(job_id="OLD-DAY", name="Dagsrapport", schedules=["16:30"], enabled=True)
    custom = mi.JobProfile(job_id="CUSTOM", name="Min egen ettermiddagsstrategi", schedules=["15:00"], enabled=True)
    repaired, changes = mi.ensure_required_report_jobs([*required, legacy, custom])
    old = next(job for job in repaired if job.job_id == "OLD-DAY")
    own = next(job for job in repaired if job.job_id == "CUSTOM")
    assert old.enabled is False and old.schedules == []
    assert own.enabled is True and own.schedules == ["15:00"]
    assert any(change["action"] == "DISABLED_DUPLICATE" for change in changes)


def test_automatic_test_has_isolated_identity(monkeypatch):
    source = mi.JobProfile(
        job_id="MI-REQUIRED-MORNING", name="Obligatorisk morgenrapport",
        schedules=["08:00"], enabled=True, scan_limit=50,
    )
    monkeypatch.setattr(mi, "load_jobs", lambda: [source])
    # build_test_job imports load_jobs from the module at call time.
    job = build_test_job(series_id="RTS-1", part=1, total=4, attempt=1)
    assert job.job_id == "MI-AUTONOMY-REPORT-TEST"
    assert job.name == "Autonomi rapporttest"
    assert job.schedules == [] and job.enabled is False


def test_required_ledger_ignores_test_history_using_production_job_id(monkeypatch):
    jobs, _ = mi.ensure_required_report_jobs([])
    monkeypatch.setattr(mi, "load_jobs", lambda: jobs)
    monkeypatch.setattr(mi, "load_job_history", lambda limit=2000: [{
        "job_id": "MI-REQUIRED-MORNING", "type": "Test",
        "trigger": "SCHEDULED_REPORT_TEST_NOTIFICATION",
        "planned_at": "2026-08-11T06:00:00+00:00", "pdf": True,
        "pushover_sent": True, "run_id": "TEST-RUN",
    }])
    ledger = mi.required_report_delivery_ledger(datetime(2026, 8, 11, 7, 0, tzinfo=timezone.utc))
    morning = ledger["rows"][0]
    assert morning["status"] == "FORSINKET"
    assert morning["run_id"] == "" and morning["pushover_sent"] is False


def test_top_scan_status_prefers_durable_paper_scanner_heartbeat(monkeypatch):
    monkeypatch.setattr(cron_control, "_utc_now", lambda: datetime(2026, 8, 11, 12, 15, tzinfo=timezone.utc))
    monkeypatch.setattr(cron_control, "load_settings", lambda: {
        "last_scan_at": "2026-07-25T21:00:00+00:00",
        "scan_interval_minutes": 15, "background_scanning_enabled": True,
    })
    monkeypatch.setattr(paper_scanner_runtime, "load_scanner_status", lambda: {
        "state": "COMPLETED", "completed_at": "2026-08-11T12:00:00+00:00",
    })
    status = cron_control.cron_status_text()
    assert status["last_scan_at"] == "2026-08-11T12:00:00+00:00"
    assert status["last_scan_source"] == "paper_scanner_status"
    assert status["scan_stale"] is False
