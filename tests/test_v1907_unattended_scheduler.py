import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch


class UnattendedSchedulerTests(unittest.TestCase):
    def test_report_repair_failure_cannot_block_scheduler(self):
        import market_intelligence
        import scheduled_runner
        import scheduler_background

        with (
            patch.object(market_intelligence, "restore_public_reports", side_effect=RuntimeError("pdf repair")),
            patch.object(scheduler_background, "run_scheduler_cycle", return_value={"state": "IDLE", "runs": 0, "error": ""}),
            patch.object(scheduled_runner, "_save", side_effect=lambda state: state),
            patch.object(scheduled_runner, "load_unattended_state", return_value={}),
        ):
            state = scheduled_runner.run_once()

        self.assertEqual(state["state"], "COMPLETED")
        self.assertEqual(state["report_repair"]["state"], "FAILED")
        self.assertEqual(state["scheduler"]["state"], "IDLE")

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
