"""Regression tests for durable fixed-slot scheduler history."""
from datetime import datetime, timezone, timedelta
from unittest.mock import patch
import market_intelligence as mi


def test_scheduled_start_without_trigger_is_recognized():
    job = mi.JobProfile(name="Morning", job_id="MI-REQUIRED-MORNING", schedules=["08:00"], timezone_name="Europe/Oslo")
    planned = datetime(2026, 11, 3, 7, tzinfo=timezone.utc)
    row = {"job_id": job.job_id, "type": "Planlagt", "planned_at": planned.isoformat(), "status": "Startet", "started_at": planned.isoformat()}
    with patch.object(mi, "load_job_history", return_value=[row]):
        assert mi._scheduled_history_for_slot_v19220_rc13(job, planned)["status"] == "Startet"
        assert mi._latest_scheduled_actual(job) is None


def test_started_slot_does_not_run_twice():
    job = mi.JobProfile(name="Morning", job_id="MI-REQUIRED-MORNING", schedules=["08:00"], timezone_name="Europe/Oslo", enabled=True)
    planned = datetime(2026, 11, 3, 7, tzinfo=timezone.utc)
    row = {"job_id": job.job_id, "type": "Planlagt", "planned_at": planned.isoformat(), "status": "Startet", "started_at": planned.isoformat()}
    with patch.object(mi, "load_job_history", return_value=[row]):
        assert not mi._slot_due(job, planned + timedelta(minutes=15), authoritative_unattended=True)
        late = mi.schedule_timeline(job, planned + timedelta(hours=2), authoritative_unattended=True)
        assert late["last_planned_status"] == "Feil"
        assert late["abandoned_scheduled_start"] is True
        assert not mi._slot_due(job, planned + timedelta(hours=2), authoritative_unattended=True)
