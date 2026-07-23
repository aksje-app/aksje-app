import unittest
from io import BytesIO

from pypdf import PdfReader

from autonomous_portfolio import AutonomousParameters
from autonomi_core.portfolio_decisions.decision_funnel import build_decision_funnel
import market_intelligence as mi


class DecisionFunnelTests(unittest.TestCase):
    def setUp(self):
        self.params = AutonomousParameters(minimum_investment_score=78, minimum_data_quality=55,
                                           maximum_risk_score=65, maximum_open_positions=12)
        self.portfolio = {"status": "ACTIVE", "cash": 500000, "positions": {}}

    def test_production_threshold_is_unchanged_and_shadow_is_read_only(self):
        rows = [
            {"ticker": "PASS.OL", "market": "Norge", "investment_score": 79, "data_quality": 80,
             "risk_score": 20, "price": 100, "portfolio_action": "BUY"},
            {"ticker": "NEAR.OL", "market": "Norge", "investment_score": 76, "data_quality": 80,
             "risk_score": 20, "price": 100, "portfolio_action": "BUY"},
        ]
        result = build_decision_funnel(rows, parameters=self.params, portfolio=self.portfolio)
        self.assertEqual(result["production_threshold"], 78)
        self.assertFalse(result["production_threshold_changed"])
        self.assertEqual(result["eligible"], 1)
        challenger = next(row for row in result["shadow_thresholds"] if row["threshold"] == 76)
        self.assertEqual(challenger["score_qualified_count"], 2)
        self.assertEqual(challenger["eligible_count"], 2)
        self.assertFalse(challenger["changes_production"])

    def test_missing_execution_quality_is_explicit(self):
        result = build_decision_funnel([
            {"ticker": "MISS", "investment_score": 90, "risk_score": 10, "price": 20, "portfolio_action": "BUY"}
        ], parameters=self.params, portfolio=self.portfolio)
        row = result["candidates"][0]
        self.assertEqual(row["data_quality_source"], "MISSING_EXECUTION_FIELD")
        self.assertIn("Datakvalitet", ";".join(row["reasons"]))

    def test_canonical_nested_last_price_is_accepted(self):
        result = build_decision_funnel([
            {"ticker": "LIVE.OL", "investment_score": 90, "data_quality": 90, "risk_score": 10,
             "portfolio_action": "BUY", "raw": {"last_price": 123.45}}
        ], parameters=self.params, portfolio=self.portfolio)
        self.assertEqual(result["candidates"][0]["price"], 123.45)
        self.assertTrue(result["candidates"][0]["gates"]["price"])

    def test_position_origin_is_reported(self):
        portfolio = {"status": "ACTIVE", "positions": {"OLD.OL": {"source_run_id": "RECOVERED-LEGACY"}}}
        result = build_decision_funnel([], parameters=self.params, portfolio=portfolio,
                                       trades=[{"ticker": "OLD.OL", "action": "RECOVERED", "recovered": True}])
        self.assertEqual(result["position_provenance"][0]["origin"], "RECOVERED")

    def test_pdf_contains_funnel_and_shadow(self):
        funnel = build_decision_funnel([
            {"ticker": "TEST.OL", "market": "Norge", "investment_score": 76, "data_quality": 80,
             "risk_score": 20, "price": 100, "portfolio_action": "BUY", "valid_for_decision": True}
        ], parameters=self.params, portfolio=self.portfolio)
        pdf = mi.build_pdf({"run_id": "MI-TEST", "created_at": "2026-07-23T08:00:00+00:00",
                            "job_name": "Test", "markets": ["Norge"], "summary": {}, "candidates": [],
                            "portfolio_decisions": {}, "decision_funnel": funnel})
        text = "\n".join((page.extract_text() or "") for page in PdfReader(BytesIO(pdf)).pages)
        self.assertIn("Beslutningstrakt og kjøpsvurdering", text)
        self.assertIn("Shadow Mode", text)


if __name__ == "__main__":
    unittest.main()
