from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import market_intelligence as mi


def test_required_reports_preserve_enabled_weekends_and_add_weekend_days():
    source = mi.JobProfile(
        job_id="MI-REQUIRED-AFTERNOON",
        name="Obligatorisk ettermiddagsrapport",
        schedules=["14:00"],
        weekdays=[0, 1, 2, 3, 4],
        allow_weekends=True,
    )
    jobs, _ = mi.ensure_required_report_jobs([source])
    afternoon = next(job for job in jobs if job.job_id == source.job_id)
    assert afternoon.allow_weekends is True
    assert afternoon.weekdays == [0, 1, 2, 3, 4, 5, 6]
    sunday = datetime(2026, 8, 16, 12, 0, tzinfo=timezone.utc).astimezone(
        __import__("zoneinfo").ZoneInfo("Europe/Oslo")
    ).date()
    assert [slot.strftime("%H:%M") for slot in mi._localized_slot(afternoon, sunday)] == ["14:00"]


def test_required_reports_remain_weekday_only_when_weekends_are_disabled():
    jobs, _ = mi.ensure_required_report_jobs([])
    afternoon = next(job for job in jobs if job.job_id == "MI-REQUIRED-AFTERNOON")
    sunday = datetime(2026, 8, 16, 12, 0, tzinfo=timezone.utc).astimezone(
        __import__("zoneinfo").ZoneInfo("Europe/Oslo")
    ).date()
    assert afternoon.allow_weekends is False
    assert afternoon.weekdays == [0, 1, 2, 3, 4]
    timeline = mi.schedule_timeline(afternoon, datetime(2026, 8, 16, 12, 0, tzinfo=timezone.utc))
    assert timeline["next_planned_local"].startswith("2026-08-17T14:00:00")


def test_expired_delivery_retry_becomes_terminal_and_is_not_retried(monkeypatch):
    jobs, _ = mi.ensure_required_report_jobs([])
    morning = jobs[0]
    run = {
        "run_id": "RUN-EXPIRED",
        "created_at": "2026-08-01T06:00:00+00:00",
        "persistence": {"ok": True},
        "pdf_delivery": {"generated": True, "validated": True, "published": True},
        "notification": {"sent": False},
    }
    monkeypatch.setattr(mi, "load_jobs", lambda: jobs)
    monkeypatch.setattr(mi, "load_job_history", lambda limit=500: [{
        "job_id": morning.job_id, "run_id": run["run_id"], "pushover_sent": False,
    }])
    monkeypatch.setattr(mi, "load_run", lambda run_id: run)
    monkeypatch.setattr(mi, "_notification", lambda job, value: (False, "Varsel utløpt: rapporten er 200 minutter gammel"))
    monkeypatch.setattr(mi, "_write", lambda path, value: run.update(value) if path.name == "RUN-EXPIRED.json" else None)
    history = []
    monkeypatch.setattr(mi, "_append_job_history", history.append)

    first = mi.retry_pending_required_report_deliveries()
    assert first["attempted"][0]["terminal"] is True
    assert run["notification"]["terminal_reason"] == "EXPIRED_REPORT"
    assert run["notification"]["attempted"] is False
    assert history[0]["status"] == "Utløpt"
    assert history[0]["pushover_attempted"] is False

    second = mi.retry_pending_required_report_deliveries()
    assert second["attempted"] == []


def test_scheduler_health_exposes_all_three_required_next_slots(monkeypatch):
    jobs, _ = mi.ensure_required_report_jobs([])
    monkeypatch.setattr(mi, "load_job_history", lambda limit=50: [])
    snapshot = mi.scheduler_health_snapshot(
        datetime(2026, 8, 16, 12, 0, tzinfo=timezone.utc),
        persist=False,
        jobs=jobs,
    )
    assert [row["job_id"] for row in snapshot["required_next"]] == [
        "MI-REQUIRED-MORNING", "MI-REQUIRED-AFTERNOON", "MI-REQUIRED-EVENING",
    ]
    assert [row["next_planned_local"][11:16] for row in snapshot["required_next"]] == [
        "08:00", "14:00", "22:00",
    ]


def test_activated_autosave_name_is_not_presented_as_draft():
    assert mi.activated_job_name_v19220_rc1631q("Utkast – USA + Norge + Sverige") == "Analyse – USA + Norge + Sverige"
    loaded = mi.JobProfile.from_dict({
        "job_id": "MIJ-LIVE", "name": "Utkast – USA + Norge + Sverige",
        "markets": ["Norge", "Sverige", "USA"],
    })
    assert loaded.name == "Analyse – USA + Norge + Sverige"


def test_portfolio_navigation_buttons_target_canonical_workspaces():
    overview = Path("autonomy_overview.py").read_text(encoding="utf-8")
    portfolio = Path("autonomous_portfolio.py").read_text(encoding="utf-8")
    navigation = Path("navigation_state.py").read_text(encoding="utf-8")
    assert '_goto("Autonom portefølje")' in overview
    assert '_goto("Læringsportefølje")' in overview
    assert '_navigate_autonomy_workspace("autonomous_portfolio")' in portfolio
    assert '_navigate_autonomy_workspace("learning_portfolio")' in portfolio
    assert '_navigate_autonomy_workspace("overview")' in portfolio
    for slug in ("overview", "autonomous_portfolio", "learning_portfolio"):
        assert f'"{slug}":' in navigation
