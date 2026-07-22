import unittest
from unittest.mock import MagicMock, patch
from pathlib import Path

from autonomi_core.learning_reporting.top_picks import build_canonical_top_picks, publish_canonical_top_picks


def record(run_id="RUN-2", *, failed=False):
    return {
        "result_id": f"RESULT-{run_id}", "run_id": run_id, "content_hash": "hash",
        "payload": {
            "run_id": run_id, "mission_id": "MISSION-1", "configuration_version": "cfg-7",
            "created_at": "2026-07-22T12:00:00+00:00",
            "completion_status": "AVBRUTT" if failed else "FULLFØRT",
            "analysis_aborted": failed, "validation": {"valid_for_ranking": not failed},
            "autonomous_chain": {"status": "OK"},
            "candidates": [
                {"ticker": "NEW.OL", "investment_score": 80, "valid_for_decision": True,
                 "portfolio_action": "BUY", "strategy_matches": ["Quality", "Value"],
                 "data_contract": {"quality": "HØY"}, "portfolio_decision": {"reasons": ["God porteføljepassasje"]}},
                {"ticker": "KEEP.OL", "investment_score": 75, "valid_for_decision": True,
                 "portfolio_action": "REVIEW", "strategy_match": "Growth"},
            ],
            "portfolio_proposal": {"allocations": [{"ticker": "NEW.OL"}]},
        },
    }


class CanonicalTopPicksTests(unittest.TestCase):
    def test_metadata_changes_and_portfolio_proposal(self):
        previous = {"result_id": "RESULT-RUN-1", "full_ranking": [
            {"ticker": "KEEP.OL", "investment_score": 70},
            {"ticker": "DROP.OL", "investment_score": 72},
        ]}
        package = build_canonical_top_picks(record(), previous)
        self.assertTrue(package["published"])
        self.assertEqual(package["top_picks"][0]["candidate_state"], "NY")
        keep = next(x for x in package["top_picks"] if x["ticker"] == "KEEP.OL")
        self.assertEqual(keep["candidate_state"], "GJENTATT")
        self.assertEqual(keep["score_delta_since_previous"], 5.0)
        self.assertEqual(package["dropped_candidates"][0]["ticker"], "DROP.OL")
        self.assertEqual(package["buy_now"][0]["ticker"], "NEW.OL")
        self.assertEqual(package["portfolio_proposal"]["allocations"][0]["ticker"], "NEW.OL")
        self.assertEqual(package["top_picks"][0]["mission_id"], "MISSION-1")
        self.assertIn("Quality", package["top_picks"][0]["strategy"])

    @patch("autonomi_core.learning_reporting.top_picks.get_storage_service")
    @patch("autonomi_core.learning_reporting.top_picks.write_json")
    @patch("autonomi_core.learning_reporting.top_picks.load_canonical_top_picks")
    def test_failed_run_never_overwrites_previous(self, load, write, storage):
        load.return_value = {"result_id": "RESULT-LAST-GOOD", "published": True}
        result = publish_canonical_top_picks(record(failed=True))
        self.assertFalse(result["published"])
        self.assertEqual(result["preserved_result_id"], "RESULT-LAST-GOOD")
        write.assert_not_called()
        storage.assert_not_called()

    @patch("autonomi_core.learning_reporting.top_picks.get_storage_service")
    @patch("autonomi_core.learning_reporting.top_picks.write_json")
    @patch("autonomi_core.learning_reporting.top_picks.load_canonical_top_picks")
    def test_success_updates_canonical_and_compatibility_views(self, load, write, get_storage):
        load.return_value = {}
        store = MagicMock()
        store.read_json.return_value = {}
        get_storage.return_value = store
        result = publish_canonical_top_picks(record())
        self.assertTrue(result["published"])
        write.assert_called_once()
        keys = [call.args[0] for call in store.write_json.call_args_list]
        self.assertIn("latest_rankings_v148.json", keys)
        self.assertIn("top_picks_result.json", keys)
        self.assertIn("canonical_buy_now.json", keys)
        self.assertIn("canonical_portfolio_proposal.json", keys)

    def test_direct_fx_navigation_exists_on_desktop_and_mobile(self):
        root = Path(__file__).resolve().parents[1]
        sidebar = (root / "ui_sidebar_stable.py").read_text(encoding="utf-8")
        app = (root / "app.py").read_text(encoding="utf-8")
        self.assertIn('"💱 Valutavarsler", "fx_alerts"', sidebar)
        self.assertIn('_mobile_nav_href_v18646("fx_alerts")', app)
        self.assertIn('("💱 Valutavarsler", render_currency_alerts_control_center_v1863af)', app)

    def test_publication_occurs_after_persistence_gate(self):
        source = (Path(__file__).resolve().parents[1] / "market_intelligence.py").read_text(encoding="utf-8")
        self.assertLess(source.index('if not persistence.get("ok")'), source.index('run["canonical_top_picks"] = publish_canonical_top_picks'))

    @patch("autonomi_core.learning_reporting.top_picks.get_storage_service")
    @patch("autonomi_core.learning_reporting.top_picks.write_json")
    @patch("autonomi_core.learning_reporting.top_picks.load_canonical_top_picks")
    def test_older_completion_cannot_replace_newer_result(self, load, write, storage):
        load.return_value = {"published": True, "result_id": "RESULT-NEWER", "created_at": "2026-07-22T13:00:00+00:00", "full_ranking": []}
        result = publish_canonical_top_picks(record())
        self.assertFalse(result["published"])
        self.assertEqual(result["preserved_result_id"], "RESULT-NEWER")
        write.assert_not_called()
        storage.assert_not_called()


if __name__ == "__main__":
    unittest.main()
