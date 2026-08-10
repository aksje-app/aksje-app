from __future__ import annotations

from types import SimpleNamespace

import market_intelligence as mi


def _valid_run(**overrides):
    value = {
        "trigger": "SCHEDULED",
        "report_test_series": {},
        "persistence": {"ok": True},
        "pdf_delivery": {"generated": True, "validated": True, "published": True},
    }
    value.update(overrides)
    return value


def test_fixed_report_delivery_override_allows_only_theoretical_decision_limitation():
    job = mi.JobProfile(name="Fast morgenrapport")
    result = mi._scheduled_report_delivery_override(
        job, _valid_run(), {"ok": False, "failed_stages": ["THEORETICAL_DECISIONS"]}
    )
    assert result["allowed"] is True
    assert "ikke beslutningsklar" in result["message"]


def test_acceptance_series_remains_fail_closed():
    job = mi.JobProfile(name="Autonomi rapporttest")
    run = _valid_run(report_test_series={"series_id": "RTS-1", "part": 1, "total": 4})
    result = mi._scheduled_report_delivery_override(
        job, run, {"ok": False, "failed_stages": ["THEORETICAL_DECISIONS"]}
    )
    assert result["allowed"] is False


def test_critical_report_failure_cannot_use_delivery_override():
    job = mi.JobProfile(name="Fast kveldsrapport")
    result = mi._scheduled_report_delivery_override(
        job, _valid_run(), {"ok": False, "failed_stages": ["REPORT"]}
    )
    assert result["allowed"] is False


def test_scheduler_continues_after_one_fixed_job_fails(monkeypatch):
    first = mi.JobProfile(name="Fast rapport A", job_id="A")
    second = mi.JobProfile(name="Fast rapport B", job_id="B")
    attempted = []

    monkeypatch.setattr(mi, "load_jobs", lambda: [first, second])
    monkeypatch.setattr(mi, "_due_slot_info", lambda *args, **kwargs: {
        "due": True, "previous_planned_utc": "2026-08-11T06:00:00+00:00",
        "next_planned_utc": "2026-08-11T20:00:00+00:00",
    })
    monkeypatch.setattr(mi, "upsert_job", lambda job: None)
    monkeypatch.setattr(mi, "_append_job_history", lambda row: None)
    monkeypatch.setattr(mi, "_audit", lambda *args, **kwargs: None)
    monkeypatch.setattr(mi, "scheduler_health_snapshot", lambda *args, **kwargs: {})

    def fake_run(job, **kwargs):
        attempted.append(job.job_id)
        if job.job_id == "A":
            raise RuntimeError("første rapport feilet")
        return {"run_id": "MI-B", "job_id": job.job_id}

    monkeypatch.setattr(mi, "run_job", fake_run)
    results = mi.run_due_jobs(authoritative_unattended=True)

    assert attempted == ["A", "B"]
    assert results[0]["scheduler_result"] == "FAILED"
    assert results[0]["job_id"] == "A"
    assert results[1]["run_id"] == "MI-B"
