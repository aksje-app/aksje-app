import unittest
from io import BytesIO

from pypdf import PdfReader

import market_intelligence as mi


class TimeAwareDraftTests(unittest.TestCase):
    def _run(self, created_at):
        return {"job_id": mi.DRAFT_JOB_ID, "job_name": "Morgenanalyse", "trigger": "MANUAL_DRAFT_TEST",
                "created_at": created_at, "timezone_name": "Europe/Oslo", "run_id": "MI-TIME",
                "markets": [], "summary": {}, "candidates": []}

    def test_midnight_draft_is_night_report(self):
        run = self._run("2026-07-22T22:25:10+00:00")  # 00:25 Europe/Oslo
        identity = mi.resolve_report_identity(run)
        self.assertEqual(identity["type"], "UTKAST")
        self.assertEqual(identity["label"], "Utkast – Nattrapport")
        self.assertTrue(mi.safe_report_filename(run).startswith("UTKAST_Nattrapport_20260723T002510"))
        self.assertNotIn("Morgenanalyse", mi.safe_report_filename(run))
        text = "\n".join((page.extract_text() or "") for page in PdfReader(BytesIO(mi.build_pdf(run))).pages)
        self.assertIn("Utkast – Nattrapport – Markedsanalyse", text)
        self.assertIn("Morgenanalyse", text)  # remains the separate job metadata

    def test_all_local_periods(self):
        cases = {
            "2026-07-23T04:00:00+00:00": "Morgenrapport",  # 06:00 local
            "2026-07-23T11:00:00+00:00": "Ettermiddagsrapport",  # 13:00 local
            "2026-07-23T17:00:00+00:00": "Kveldsrapport", # 19:00 local
            "2026-07-23T23:00:00+00:00": "Nattrapport",   # 01:00 local
        }
        for created, expected in cases.items():
            self.assertIn(expected, mi.resolve_report_identity(self._run(created))["label"])


if __name__ == "__main__":
    unittest.main()
