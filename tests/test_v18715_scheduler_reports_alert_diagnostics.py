import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]


class V18715ReleaseTests(unittest.TestCase):
    def test_version_and_two_independent_workers(self):
        version = (ROOT / "app_version.py").read_text(encoding="utf-8")
        runtime = (ROOT / "runtime_background.py").read_text(encoding="utf-8")
        self.assertIn('APP_VERSION = "v18.', version)
        self.assertIn("v18.7.15: Reliable Autonomy Scheduling", version)
        self.assertIn('name="fx-alert-runtime"', runtime)
        self.assertIn('name="report-scheduler-runtime"', runtime)
        self.assertIn("run_scheduler_cycle()", runtime)

    def test_direct_pdf_publish_and_render_url(self):
        import report_delivery

        run = {}
        with tempfile.TemporaryDirectory() as folder, \
                patch.object(report_delivery, "PUBLIC_REPORT_DIR", Path(folder)), \
                patch.dict(os.environ, {"RENDER_EXTERNAL_URL": "https://aksje-app.onrender.com"}, clear=False):
            target = report_delivery.publish_pdf(run, b"%PDF-test")
            self.assertEqual(target.read_bytes(), b"%PDF-test")
            url = report_delivery.public_report_url(run)
            self.assertTrue(url.startswith("https://aksje-app.onrender.com/?public_report_token="))
            self.assertNotIn("/app/static/reports/", url)
            self.assertIn("rapport_analyse", target.name)
            self.assertGreaterEqual(len(run.get("public_report_token", "")), 32)

    def test_streamlit_static_serving_is_enabled(self):
        config = (ROOT / ".streamlit" / "config.toml").read_text(encoding="utf-8")
        self.assertIn("enableStaticServing = true", config)

    def test_full_alert_chain_is_in_responsive_second_row(self):
        source = (ROOT / "app.py").read_text(encoding="utf-8")
        self.assertIn("action_left, action_mid = st.columns(2)", source)
        self.assertIn("action_test, action_diag = st.columns(2)", source)
        self.assertIn('"Test hele varselkjeden"', source)
        block = source[source.index('"Test hele varselkjeden"'):source.index('"Test hele varselkjeden"') + 500]
        self.assertIn('width="stretch"', block)

    def test_morning_jobs_default_to_always_notify(self):
        source = (ROOT / "market_intelligence.py").read_text(encoding="utf-8")
        self.assertIn('if "morgen" in str(job.name or "").casefold():', source)
        self.assertIn('return "ALWAYS"', source)
        self.assertIn('"Send alltid når rapporten er ferdig"', source)

    def test_archive_carries_direct_report_identity(self):
        source = (ROOT / "market_intelligence.py").read_text(encoding="utf-8")
        self.assertIn('"public_pdf_name": run.get("public_pdf_name")', source)
        self.assertIn('"report_url": report_public_url(run)', source)
        self.assertIn("def restore_public_reports", source)


if __name__ == "__main__":
    unittest.main()
