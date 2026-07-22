import unittest
from pathlib import Path
from unittest.mock import patch

from autonomi_core.runtime.parallel_validation import build_parallel_validation, refresh_parallel_outcomes


def sample_run():
    return {
        "run_id": "RUN-1893", "mission_id": "MISSION-1",
        "candidates": [
            {"ticker": "AAA.OL", "investment_score": 80, "confidence_score": 90, "valid_for_decision": True, "strategy_scores": {"Quality": 85}, "strategy_matches": ["Quality"], "portfolio_action": "BUY", "data_contract": {"source": "LIVE"}},
            {"ticker": "BBB", "investment_score": 70, "confidence_score": 80, "valid_for_decision": True, "strategy_scores": {"Value": 72}, "strategy_matches": ["Value"], "portfolio_action": "REVIEW", "data_contract": {"source": "CACHE"}},
        ],
        "portfolio_decisions": {"decisions": [{"ticker": "AAA.OL", "action": "BUY", "portfolio_assessed": True}, {"ticker": "BBB", "action": "REVIEW", "portfolio_assessed": True}], "actions": {"BUY": 1, "REVIEW": 1}, "portfolio_context": {"source": "PostgreSQL"}},
        "data_contract": {"evaluated": 2, "valid_for_decision": 2, "blocked": []},
        "data_refresh": {"live_attempt_count": 2, "live_count": 1, "cache_count": 1, "error_count": 0},
    }


class ParallelValidationTests(unittest.TestCase):
    def test_legacy_remains_authoritative_and_shadow_is_read_only(self):
        result = build_parallel_validation(sample_run(), total_runtime_seconds=12.3)
        self.assertEqual(result["authoritative_chain"], "LEGACY")
        self.assertTrue(result["authority_preserved"])
        self.assertEqual(result["mode"], "SHADOW_READ_ONLY")
        self.assertIn("TOP_PICKS", result["writes_blocked"])
        self.assertEqual(result["comparison"]["api_usage"]["shadow_additional_calls"], 0)

    def test_all_required_comparisons_and_horizons_exist(self):
        comparison = build_parallel_validation(sample_run())["comparison"]
        for key in ("candidates", "source_and_search", "ranking", "decisions", "data_quality", "portfolio_risk", "runtime", "api_usage", "outcomes"):
            self.assertIn(key, comparison)
        self.assertEqual(set(comparison["outcomes"]), {"5", "30", "90"})

    @patch("historical_learning.run_horizon_performance")
    @patch("autonomi_core.runtime.parallel_validation.write_json")
    def test_mature_results_compare_shadow_to_authority(self, _write, performance):
        performance.side_effect = [
            {"5": {"status": "READY", "average_return_pct": 2}, "30": {"status": "PENDING"}, "90": {"status": "PENDING"}},
            {"5": {"status": "READY", "average_return_pct": 3.5}, "30": {"status": "PENDING"}, "90": {"status": "PENDING"}},
        ]
        result = refresh_parallel_outcomes(build_parallel_validation(sample_run()))
        self.assertEqual(result["comparison"]["outcomes"]["5"]["shadow_minus_authoritative_pct"], 1.5)

    def test_integration_occurs_after_authoritative_publication(self):
        source = (Path(__file__).resolve().parents[1] / "market_intelligence.py").read_text(encoding="utf-8")
        self.assertLess(source.index('run["canonical_top_picks"] ='), source.index("build_parallel_validation(run"))


if __name__ == "__main__": unittest.main()
