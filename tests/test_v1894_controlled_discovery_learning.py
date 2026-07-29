import unittest
from pathlib import Path
from unittest.mock import patch

from autonomi_core.discovery_data.controlled_learning import create_challenger_proposals, measure_discovery_learning, queue_challenger_approval


def records(count=3):
    result = []
    for run in range(count):
        candidates = []
        for index in range(4):
            candidates.append({"ticker": f"T{run}{index}", "source": "Source A" if index < 3 else "Source B", "strategies": ["Quality"], "market": "Norge", "sector": "Energy", "discovery_bucket": "EXPERIMENTAL" if index == 3 else "NEW", "action": "BUY"})
        result.append({"comparison": {"outcomes": {"5": {"status": "READY", "shadow": {"average_return_pct": 2.5}}}}, "shadow_candidates": candidates})
    return result


class ControlledDiscoveryLearningTests(unittest.TestCase):
    def test_measures_all_required_dimensions_without_production_change(self):
        analysis = measure_discovery_learning(records())
        for key in ("sources", "strategies", "novelty", "markets", "sectors", "false_positives", "exploration_value"):
            self.assertIn(key, analysis)
        self.assertFalse(analysis["production_changed"])

    @patch("autonomi_core.discovery_data.controlled_learning.get_storage_service")
    @patch("autonomi_core.configuration.registry.read", return_value={"documented_pct": 70, "new_pct": 20, "experimental_pct": 10})
    def test_proposals_are_challengers_and_require_approval(self, _read, storage_factory):
        storage_factory.return_value.read_json.return_value = []
        proposals = create_challenger_proposals(measure_discovery_learning(records()))
        self.assertEqual({p["type"] for p in proposals}, {"EXPLORATION_SHARE", "SOURCE_PRIORITY", "STRATEGY_WEIGHT", "SEARCH_HYPOTHESIS"})
        self.assertTrue(all(p["status"] == "CHALLENGER_TESTING" and p["approval_required"] and not p["production_active"] for p in proposals))

    @patch("autonomi_core.configuration.registry.propose", return_value={"approval_id": "CAP-1", "status": "PENDING"})
    @patch("autonomi_core.discovery_data.controlled_learning.get_storage_service")
    def test_queue_uses_central_explicit_approval(self, storage_factory, propose):
        item = {"proposal_id": "DCL-1", "status": "CHALLENGER_TESTING", "path": "analysis.challenger.strategy_weights", "after": {"Quality": 1.05}, "reason": "test"}
        storage_factory.return_value.read_json.return_value = [item]
        result = queue_challenger_approval("DCL-1")
        self.assertEqual(result["status"], "PENDING_APPROVAL")
        self.assertEqual(result["central_approval_id"], "CAP-1")
        propose.assert_called_once()

    def test_report_button_has_visible_normal_and_hover_styles(self):
        source = (Path(__file__).resolve().parents[1] / "autonomy_overview.py").read_text(encoding="utf-8")
        self.assertIn("background:#172033!important", source)
        self.assertIn("color:#fff!important", source)
        self.assertIn(":hover", source)


if __name__ == "__main__": unittest.main()
