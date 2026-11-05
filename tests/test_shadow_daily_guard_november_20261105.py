from datetime import datetime, timezone
from unittest.mock import patch

from services.shadow_daily_guard import send_daily_if_due


def test_scheduler_wired_daily_watch_sends_in_november():
    now = datetime(2026, 11, 5, 12, tzinfo=timezone.utc)
    saved = {}
    report = {"date": "2026-11-05", "status": "GUL", "registrations": 1,
              "evaluations": 1, "active": 91, "matured": 0,
              "strategy_readiness": "NOT_VALIDATED", "production_changed": False,
              "failures": []}
    with patch("services.shadow_daily_guard.read_json", return_value={}), \
         patch("services.shadow_daily_guard.write_json", side_effect=lambda *args: saved.update(args[2])), \
         patch("services.shadow_daily_guard.evaluate", return_value=report), \
         patch("notifier.send_pushover_alert", return_value=(True, "HTTP 200")) as sender:
        result = send_daily_if_due(now=now)
    assert result["delivery_status"] == "SENT"
    assert saved["2026-11-05"]["sent"] is True
    assert sender.call_args.kwargs["relevance_event"] is None
    assert "NOT_VALIDATED" in sender.call_args.args[0]
