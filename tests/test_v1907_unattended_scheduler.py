import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch


class UnattendedSchedulerTests(unittest.TestCase):
    def test_report_repair_failure_cannot_block_scheduler(self):
        import inspect
        import market_intelligence
        import scheduled_runner
        with patch.object(market_intelligence, "restore_public_reports", side_effect=RuntimeError("pdf repair")):
            result = scheduled_runner._repair_public_reports()
        self.assertEqual(result["state"], "FAILED")
        self.assertIn("pdf repair", result["error"])
        # The actual schedule check precedes this independent maintenance helper.
        source = inspect.getsource(scheduled_runner._run_once_locked)
        self.assertLess(source.index("run_scheduler_cycle("), source.index("_repair_public_reports()"))

    def test_fixed_schedule_is_caught_up_after_web_process_was_asleep(self):
        import market_intelligence as mi

        job = mi.JobProfile(
            name="Morgenanalyse",
            enabled=True,
            weekdays=[3],
            schedules=["08:30"],
            scan_windows=[],
            timezone_name="Europe/Oslo",
            last_run_at="2026-07-22T20:36:10+00:00",
        )
        # Thursday 23 July 2026 at 10:16 Europe/Oslo.
        now = datetime(2026, 7, 23, 8, 16, tzinfo=timezone.utc)
        self.assertTrue(mi._slot_due(job, now))

    def test_blueprint_has_independent_cron_process(self):
        source = Path("render.yaml").read_text(encoding="utf-8")
        self.assertIn("type: cron", source)
        self.assertIn('schedule: "*/15 * * * *"', source)
        self.assertIn("startCommand: python scheduled_runner.py", source)


if __name__ == "__main__":
    unittest.main()
