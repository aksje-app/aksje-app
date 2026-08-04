from datetime import datetime
from zoneinfo import ZoneInfo

import market_intelligence as mi


def test_legacy_schedule_values_are_migrated():
    job = mi.JobProfile.from_dict({"name": "Fast", "schedules": ["08:30", "22:30"]})
    assert job.schedules == ["08:00", "22:00"]


def test_new_default_schedule_uses_requested_times():
    assert mi.JobProfile(name="Fast").schedules == ["08:00", "22:00"]
    assert "08:00" in mi.SCHEDULE_OPTIONS
    assert "22:00" in mi.SCHEDULE_OPTIONS
    assert "08:30" not in mi.SCHEDULE_OPTIONS
    assert "22:30" not in mi.SCHEDULE_OPTIONS


def test_global_alert_score_applies_to_all_new_runs(monkeypatch):
    monkeypatch.setattr(mi, "load_global_alert_score", lambda: 75.0)
    original = mi.JobProfile(name="Test", min_alert_score=80.0)
    manual, manual_meta = mi.apply_execution_settings(original)
    scheduled, scheduled_meta = mi.apply_execution_settings(original)
    assert manual.min_alert_score == 75.0
    assert scheduled.min_alert_score == 75.0
    assert manual_meta == scheduled_meta
    assert original.min_alert_score == 80.0


def test_execution_setting_is_snapshotted_at_start(monkeypatch):
    values = iter([75.0, 82.0])
    monkeypatch.setattr(mi, "load_global_alert_score", lambda: next(values))
    job = mi.JobProfile(name="Test", min_alert_score=80.0)
    first, _ = mi.apply_execution_settings(job)
    second, _ = mi.apply_execution_settings(job)
    assert first.min_alert_score == 75.0
    assert second.min_alert_score == 82.0
    assert first.min_alert_score == 75.0


def test_schedule_timeline_uses_new_morning_slot():
    job = mi.JobProfile(name="Morgen", schedules=["08:00"], weekdays=[0, 1, 2, 3, 4], enabled=True)
    now = datetime(2026, 8, 4, 8, 1, tzinfo=ZoneInfo("Europe/Oslo"))
    timeline = mi.schedule_timeline(job, now)
    assert "08:00" in str(timeline)
