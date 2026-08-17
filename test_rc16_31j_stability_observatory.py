from pathlib import Path
import unittest

from app_version import APP_VERSION, PREVIOUS_APP_VERSION
from autonomi_core.runtime.parallel_validation import build_parallel_validation


ROOT = Path(__file__).resolve().parents[1]


class StabilityObservatoryTests(unittest.TestCase):
    def test_release_identity_is_unambiguous(self):
        self.assertEqual(APP_VERSION, "v19.22.0-rc16.31j")
        self.assertEqual(PREVIOUS_APP_VERSION, "v19.22.0-rc16.31i")

    def test_quarantine_blocks_decision_not_evidence_attempt(self):
        source = (ROOT / "investment_pipeline.py").read_text(encoding="utf-8")
        self.assertIn("evidence_quarantine_override", source)
        self.assertIn("TOP_RANKED_MINIMUM", source)
        self.assertNotIn(
            'if ticker in source_by_ticker and not bool(source_by_ticker[ticker].get("analysis_quarantine"))',
            source,
        )
        self.assertIn('"evidence_observability"', source)
        self.assertIn('"top3_complete"', source)

    def test_shadow_disagreement_is_red_and_candidate_explained(self):
        run = {
            "run_id": "RUN-J",
            "candidates": [{
                "ticker": "AAA.OL", "investment_score": 68, "confidence_score": 80,
                "valid_for_decision": True, "strategy_scores": {"Quality": 82},
                "strategy_matches": ["Quality"], "portfolio_action": "BUY",
                "decision_gates": [{"gate": "EVIDENCE", "passed": False, "reason": "Nyhetsdekning mangler"}],
            }],
            "portfolio_decisions": {"decisions": [{"ticker": "AAA.OL", "action": "REVIEW"}]},
        }
        result = build_parallel_validation(run)
        gate = result["validation_gate"]
        diff = result["comparison"]["decisions"]["diff"]
        self.assertEqual(gate["status"], "RED")
        self.assertTrue(gate["promotion_blocked"])
        self.assertEqual(diff[0]["reason_category"], "EVIDENCE")
        self.assertEqual(diff[0]["ticker"], "AAA.OL")

    def test_mobile_delivery_makes_download_primary_and_external_secondary(self):
        overview = (ROOT / "autonomy_overview.py").read_text(encoding="utf-8")
        reports = (ROOT / "market_intelligence.py").read_text(encoding="utf-8")
        self.assertIn("Last ned PDF – kan deles", overview)
        self.assertIn("Ekstern offentlig PDF", overview)
        self.assertIn("Last ned full rapport med vedlegg", reports)
        self.assertIn("Last ned kort rapport (3 sider)", reports)
        self.assertIn("kan denne lenken forlate appen", reports)

    def test_full_system_check_covers_operational_risks(self):
        source = (ROOT / "report_system_check.py").read_text(encoding="utf-8")
        for label in ("Paper-skanner", "Shadow-avviksport", "Kandidatevidens", "Lagringsretensjon"):
            self.assertIn(label, source)


if __name__ == "__main__":
    unittest.main()
