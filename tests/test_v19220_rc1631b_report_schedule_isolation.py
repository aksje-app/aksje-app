from __future__ import annotations

from datetime import datetime, timezone
import sys
from types import SimpleNamespace

import app_version
import market_intelligence as mi
import report_test_mode


def test_release_version_is_rc1631b():
    assert app_version.APP_VERSION == "v19.22.0-rc16.31b"
    assert app_version.PREVIOUS_APP_VERSION == "v19.22.0-rc16.31a"


def test_fixed_jobs_have_only_their_canonical_slot():
    jobs, _ = mi.ensure_required_report_jobs([])
    assert [(job.job_id, job.schedules, job.scan_windows) for job in jobs] == [
        ("MI-REQUIRED-MORNING", ["08:00"], []),
        ("MI-REQUIRED-AFTERNOON", ["14:00"], []),
        ("MI-REQUIRED-EVENING", ["22:00"], []),
    ]
    oslo_day = datetime(2026, 8, 12, 12, 0, tzinfo=timezone.utc).astimezone(
        __import__("zoneinfo").ZoneInfo("Europe/Oslo")
    ).date()
    assert [[slot.strftime("%H:%M") for slot in mi._localized_slot(job, oslo_day)] for job in jobs] == [
        ["08:00"], ["14:00"], ["22:00"],
    ]


def test_test_job_is_not_a_clone_of_a_production_profile():
    job = report_test_mode.build_test_job(series_id="RTS-CLEAN", part=1, total=4, attempt=1)
    assert job.job_id == "MI-AUTONOMY-REPORT-TEST"
    assert job.schedules == [] and job.scan_windows == []
    assert job.report_test_series_id == "RTS-CLEAN"


def test_fixed_job_cannot_be_presented_as_automatic_test(monkeypatch):
    captured = {}
    monkeypatch.setattr(mi, "_read", lambda *args, **kwargs: {})
    monkeypatch.setattr(mi, "_write", lambda *args, **kwargs: None)
    monkeypatch.setattr(mi, "_audit", lambda *args, **kwargs: None)
    monkeypatch.setitem(sys.modules, "notifier", SimpleNamespace(
        send_pushover_alert=lambda message, title="", **kwargs: (captured.update(message=message, title=title) or True, None),
    ))
    job = mi.JobProfile(
        job_id="MI-REQUIRED-EVENING", name="Obligatorisk kveldsrapport",
        notification_mode="ALWAYS", notify_only_changes=False,
    )
    run = {
        "run_id": "RUN-FIXED", "created_at": datetime.now(timezone.utc).isoformat(),
        "trigger": "SCHEDULED", "test_run": False, "suppress_notifications": False,
        "markets": ["Norge", "Sverige", "USA"], "summary": {"deep_analyzed": 10},
        "changes": {"new": [], "improved": []}, "candidates": [], "proposals": [],
        "report_test_series": {"series_id": "RTS-STALE", "part": 4, "total": 4, "attempt": 4, "automatic": True},
    }
    ok, _ = mi._notification(job, run)
    assert ok is True
    assert "AUTOMATISK" not in captured["title"]
    assert "AUTOMATISK RAPPORTTEST" not in captured["message"]


def test_duplicate_receipt_is_idempotent_success(monkeypatch):
    job = mi.JobProfile(job_id="MI-REQUIRED-MORNING", name="Obligatorisk morgenrapport")
    monkeypatch.setattr(mi, "_read", lambda *args, **kwargs: {"RUN-SENT": {"sent": True}})
    ok, detail = mi._notification(job, {"run_id": "RUN-SENT"})
    assert ok is True
    assert detail.startswith("Allerede levert")
