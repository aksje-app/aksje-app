import unittest

from autonomi_core.analysis_ranking.layer import STRATEGIES, analyze_candidate


GOOD_DERIVED = {"fundamental": 82, "risk": 22, "discovery": 78, "confidence": 88}


class AnalysisRankingLayerTests(unittest.TestCase):
    def test_parallel_strategies_and_no_universal_score(self):
        result = analyze_candidate({
            "sector": "Technology", "forward_pe": 25, "earnings_growth": .30,
            "dividend_yield": .03, "technical_score": 82, "insider_score": 78,
            "news_score": 76, "max_drawdown_pct": -25, "return_1m": .08,
        }, GOOD_DERIVED, adaptive_meta={"mode": "APPROVED", "model_version": "A-1"})
        self.assertEqual(set(result["strategies"]), set(STRATEGIES))
        self.assertGreaterEqual(len(result["matches"]), 2)
        self.assertFalse(result["universal_score_created"])
        self.assertEqual(result["adaptive_ranking"]["model_version"], "A-1")

    def test_every_score_is_explainable_and_sector_aware(self):
        result = analyze_candidate({"sector": "Energy", "forward_pe": 10, "dividend_yield": .08}, GOOD_DERIVED)
        self.assertEqual(result["sector"], "Energy")
        self.assertEqual(result["sector_benchmark"]["pe_anchor"], 12)
        for assessment in result["strategies"].values():
            self.assertEqual(assessment["sector"], "Energy")
            self.assertTrue(any(item["component"] == "sector_context" for item in assessment["contributions"]))
            for item in assessment["contributions"]:
                self.assertIn("raw_value", item)
                self.assertIn("weight", item)
                self.assertIn("contribution", item)

    def test_same_valuation_is_interpreted_by_sector(self):
        technology = analyze_candidate({"sector": "Technology", "forward_pe": 28}, GOOD_DERIVED)
        energy = analyze_candidate({"sector": "Energy", "forward_pe": 28}, GOOD_DERIVED)
        tech_value = next(x for x in technology["strategies"]["Value"]["contributions"] if x["component"] == "valuation")
        energy_value = next(x for x in energy["strategies"]["Value"]["contributions"] if x["component"] == "valuation")
        self.assertGreater(tech_value["component_score"], energy_value["component_score"])

    def test_missing_evidence_is_explicit_and_reduces_confidence(self):
        sparse = analyze_candidate({"sector": "Healthcare"}, GOOD_DERIVED)
        full = analyze_candidate({"sector": "Healthcare", "forward_pe": 24, "earnings_growth": .20, "dividend_yield": .03, "technical_score": 75, "insider_score": 70, "news_score": 70, "max_drawdown_pct": -20, "return_1m": .05}, GOOD_DERIVED)
        self.assertTrue(sparse["strategies"]["Insider"]["missing_data"])
        self.assertLess(sparse["strategies"]["Insider"]["confidence"], full["strategies"]["Insider"]["confidence"])

    def test_scenarios_are_strategy_specific_not_price_forecasts(self):
        result = analyze_candidate({"sector": "Industrials", "technical_score": 70}, GOOD_DERIVED)
        self.assertEqual(set(result["scenario_analysis"]["base"]), set(STRATEGIES))
        self.assertIn("ikke kursmål", result["scenario_analysis"]["note"])


if __name__ == "__main__": unittest.main()
