import json
import unittest
from pathlib import Path
from unittest.mock import patch

import insider_intelligence
import manual_job_background as background
import market_intelligence as mi


ROOT = Path(__file__).resolve().parents[1]


class LiveProgressPerformanceDecisionEvidenceTests(unittest.TestCase):
    def setUp(self):
        self.memory = {}
        self.write_patch = patch.object(background, "write_json", side_effect=self._write)
        self.read_patch = patch.object(background, "read_json", side_effect=self._read)
        self.write_patch.start(); self.read_patch.start(); background._THREADS.clear()

    def tearDown(self):
        for thread in list(background._THREADS.values()):
            thread.join(timeout=2)
        self.write_patch.stop(); self.read_patch.stop(); background._THREADS.clear()

    def _write(self, key, path, value):
        self.memory[key] = json.loads(json.dumps(value, default=str))

    def _read(self, key, path, default):
        return json.loads(json.dumps(self.memory.get(key, default)))

    def test_failed_job_keeps_honest_percent_and_diagnostics(self):
        with patch.object(mi, "run_job", side_effect=ValueError("konfigurasjonsversjon samsvarer ikke")):
            accepted = background.start_manual_job(mi.JobProfile(name="Feiltest"), trigger="MANUAL_SIMPLE_AUTONOMY")
            for thread in list(background._THREADS.values()):
                thread.join(timeout=2)
        status = background.get_status(accepted["execution_id"])
        self.assertEqual(status["state"], "FAILED")
        self.assertLess(status["percent"], 100)
        self.assertEqual(status["error_stage"], "PREFLIGHT")
        self.assertEqual(status["error_type"], "ValueError")
        self.assertIn("konfigurasjonsversjon", status["error"])
        self.assertTrue(status["error_trace"])

    def test_overview_uses_isolated_live_fragment(self):
        source = (ROOT / "autonomy_overview.py").read_text(encoding="utf-8")
        self.assertIn('fragment(run_every="5s")', source)
        self.assertIn("_render_live_progress", source)
        self.assertIn("Vis teknisk diagnostikk", source)
        self.assertIn("Markedsgjennomføring", source)

    def test_pdf_has_decision_evidence_and_clear_source_name(self):
        source = (ROOT / "market_intelligence.py").read_text(encoding="utf-8")
        for text in ("Kursdatakilde", "Konkret beslutningsbevis for den viste listen", "Insiderbevis", "Nyhetsbevis", "Ingen kjøpsvekt"):
            self.assertIn(text, source)
        self.assertNotIn('– investeringsforslag", styles["Section"]', source)

    def test_net_insider_sales_cannot_be_positive(self):
        rows = [
            {"date": "2026-07-20", "transaction": "purchase", "shares": 10, "price": 10, "insider": "A"},
            {"date": "2026-07-20", "transaction": "sale", "shares": 1000, "price": 100, "insider": "B"},
        ]
        result = insider_intelligence.score_transactions("TEST", rows)
        self.assertLess(result["net_value"], 0)
        self.assertLess(result["score"], 62)
        self.assertNotIn("POSITIV", result["signal"])


if __name__ == "__main__":
    unittest.main()
