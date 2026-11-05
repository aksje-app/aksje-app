from datetime import datetime, timezone
from unittest.mock import patch

from services.shadow_daily_guard import evaluate, send_daily_if_due


def test_guard_does_not_mark_missing_evaluations_green():
    now = datetime(2026, 10, 17, 14, tzinfo=timezone.utc)
    with patch("services.shadow_daily_guard.read_events", return_value=[]), patch(
        "services.shadow_daily_guard.read_json", return_value={}
    ):
        row = evaluate(now)
    assert row["status"] == "RØD"
    assert len(row["failures"]) == 3


def test_daily_monitoring_continues_after_original_seven_day_window():
    now = datetime(2026, 10, 24, 14, tzinfo=timezone.utc)
    with patch("services.shadow_daily_guard.read_json", return_value={}), patch(
        "services.shadow_daily_guard.evaluate", return_value={
            "date": "2026-10-24", "status": "GUL", "failures": [],
            "registrations": 1, "evaluations": 1, "active": 91,
            "matured": 0, "strategy_readiness": "NOT_VALIDATED",
            "production_changed": False,
        }
    ), patch("notifier.send_pushover_alert", return_value=(True, "OK")), patch(
        "notifier.normalize_notification_result", return_value=(True, "OK")
    ), patch("services.shadow_daily_guard.write_json") as writer:
        result = send_daily_if_due(now=now)
    assert result["delivery_status"] == "SENT"
    assert writer.call_args.args[2]["2026-10-24"]["sent"] is True


def test_successful_delivery_records_receipt():
    now = datetime(2026, 10, 18, 14, tzinfo=timezone.utc)
    mocked = {"date": "2026-10-18", "status": "GUL", "failures": [],
              "registrations": 1, "evaluations": 1, "active": 91,
              "matured": 0, "strategy_readiness": "NOT_VALIDATED",
              "production_changed": False}
    with patch("services.shadow_daily_guard.read_json", return_value={}), patch(
        "services.shadow_daily_guard.evaluate", return_value=mocked
    ), patch("notifier.send_pushover_alert", return_value=(True, "OK")), patch(
        "notifier.normalize_notification_result", return_value=(True, "OK")
    ), patch("services.shadow_daily_guard.write_json") as writer:
        row = send_daily_if_due(now=now)
    assert row["sent"] is True
    assert writer.call_args.args[2]["2026-10-18"]["sent"] is True


def test_duplicate_suppression_not_counted_as_delivered():
    now = datetime(2026, 10, 18, 14, tzinfo=timezone.utc)
    mocked = {"date": "2026-10-18", "status": "GUL", "failures": [],
              "registrations": 1, "evaluations": 1, "active": 91,
              "matured": 0, "strategy_readiness": "NOT_VALIDATED",
              "production_changed": False}
    with patch("services.shadow_daily_guard.read_json", return_value={}), patch(
        "services.shadow_daily_guard.evaluate", return_value=mocked
    ), patch("notifier.send_pushover_alert", return_value=(True, "duplicate suppressed by durable fingerprint")), patch(
        "notifier.normalize_notification_result", return_value=(True, "duplicate suppressed by durable fingerprint")
    ), patch("services.shadow_daily_guard.write_json") as writer:
        row = send_daily_if_due(now=now)
    assert row["sent"] is False
    assert row["delivery_status"] == "DUPLICATE_SUPPRESSED"
    assert writer.call_args.args[2]["2026-10-18"]["sent"] is False
