from pathlib import Path
import unittest
from unittest.mock import patch

import market_intelligence as mi


ROOT = Path(__file__).resolve().parents[1]


class ReportNotificationControlTests(unittest.TestCase):
    def test_report_identity_uses_actual_oslo_time(self):
        cases = [
            ("2026-07-23T06:00:00+00:00", "MORGENRAPPORT"),
            ("2026-07-23T13:00:00+00:00", "DAGSRAPPORT"),
            ("2026-07-23T17:00:00+00:00", "KVELDSRAPPORT"),
            ("2026-07-23T01:00:00+00:00", "NATTRAPPORT"),
        ]
        for timestamp, expected in cases:
            with self.subTest(timestamp=timestamp):
                identity = mi.report_identity(
                    "SCHEDULED", "Morgenanalyse", "MIJ-1",
                    created_at=timestamp, timezone_name="Europe/Oslo",
                )
                self.assertEqual(identity["type"], expected)

    def test_draft_identity_overrides_clock(self):
        identity = mi.report_identity(
            "MANUAL_DRAFT_TEST", "Morgenanalyse", mi.DRAFT_JOB_ID,
            created_at="2026-07-23T17:00:00+00:00", timezone_name="Europe/Oslo",
        )
        self.assertEqual(identity["type"], "UTKAST")

    def test_duplicate_run_notification_is_blocked_before_delivery(self):
        job = mi.JobProfile(name="Morgenanalyse", job_id="MIJ-1")
        with patch.object(mi, "_read", return_value={"MI-1": {"sent": True}}):
            ok, detail = mi._notification(job, {"run_id": "MI-1"})
        self.assertFalse(ok)
        self.assertIn("Duplikat blokkert", detail)

    def test_polling_exists_only_for_running_status(self):
        source = (ROOT / "autonomy_overview.py").read_text(encoding="utf-8")
        self.assertIn("if running and callable(fragment):", source)
        self.assertIn('fragment(run_every="5s")', source)

    def test_simple_mode_and_mobile_expose_reports(self):
        simple = (ROOT / "autonomy_modes.py").read_text(encoding="utf-8")
        app = (ROOT / "app.py").read_text(encoding="utf-8")
        self.assertIn("📄 Åpne siste rapport", simple)
        self.assertIn("📚 Rapportarkiv", simple)
        self.assertGreaterEqual(app.count("title=\"Rapporter\""), 2)
        self.assertIn("overflow-x: auto", app)


if __name__ == "__main__":
    unittest.main()
