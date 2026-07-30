import unittest
from pathlib import Path

from autonomi_core.runtime.full_execution import STAGES, build_full_execution_receipt, execution_manifest, prepublication_gate


def complete_run():
    candidate = {
        "ticker": "TEST.OL", "investment_score": 80, "analysis_ranking": {"version": "v18.8.8"},
        "strategy_scores": {"Quality": 82}, "strategy_matches": ["Quality"],
    }
    return {
        "run_id": "RUN-1892", "mission_id": "MISSION-1892", "configuration_version": "cfg-1",
        "markets": ["Norge"], "market_runs": [{"market": "Norge"}],
        "portfolio_need_preflight": {
            "read_at": "2026-07-22T10:00:00+00:00", "source": "PostgreSQL",
            "position_count": 2, "needs": [], "context": {"position_count": 2},
        },
        "portfolio_decisions": {
            "portfolio_context": {"position_count": 2},
            "decisions": [{"ticker": "TEST.OL", "portfolio_assessed": True}],
            "actions": {"BUY": 1},
        },
        "discovery_data": {"markets": [{"market": "Norge"}], "selected": 25},
        "candidates": [candidate], "changes": {"new": [candidate]},
        "canonical_top_picks": {"published": True, "result_id": "RESULT-RUN-1892", "top_picks": [candidate]},
        "autonomous_chain": {"status": "OK", "execution": "THEORETICAL_ONLY", "stages": [{"name": "AUTONOMOUS_PORTFOLIO", "status": "OK"}]},
        "persistence": {"ok": True, "archive_saved": True, "run_json_saved": True}, "pdf_path": "report.pdf",
        "notification": {"sent": True, "required": True, "detail": "Sendt"},
        "canonical_result": {"stored_once": True, "result_id": "RESULT-RUN-1892"},
        "historical_learning": {"snapshots_created": 1},
    }


class FullAutonomyExecutionTests(unittest.TestCase):
    def test_manifest_has_exactly_thirteen_self_contained_steps(self):
        manifest = execution_manifest()
        self.assertEqual(len(STAGES), 13)
        self.assertEqual(len(manifest["stages"]), 13)
        self.assertEqual(manifest["manual_dependencies"], [])

    def test_complete_run_is_self_contained(self):
        receipt = build_full_execution_receipt(complete_run())
        self.assertEqual(receipt["status"], "COMPLETED")
        self.assertTrue(receipt["self_contained"])
        self.assertEqual(receipt["completed_steps"], 13)
        self.assertEqual(receipt["manual_dependencies"], [])

    def test_disabled_decision_engine_fails_closed(self):
        run = complete_run()
        run["autonomous_chain"]["stages"][0]["status"] = "DISABLED"
        receipt = build_full_execution_receipt(run)
        self.assertFalse(receipt["self_contained"])
        self.assertIn("THEORETICAL_DECISIONS", receipt["failed_stages"])
        self.assertFalse(prepublication_gate(run)["ok"])

    def test_required_notification_failure_fails_and_blocks_top_pick_commit_order(self):
        run = complete_run()
        run["notification"] = {"sent": False, "required": True, "detail": "Pushover timeout"}
        receipt = build_full_execution_receipt(run)
        self.assertIn("NOTIFICATIONS", receipt["failed_stages"])
        source = (Path(__file__).resolve().parents[1] / "market_intelligence.py").read_text(encoding="utf-8")
        self.assertLess(source.index("notify_ok, notify_detail"), source.index('run["canonical_top_picks"] = (publish_canonical_top_picks'))

    def test_readability_and_thirteen_step_overview_are_present(self):
        source = (Path(__file__).resolve().parents[1] / "autonomy_overview.py").read_text(encoding="utf-8")
        self.assertIn("min-height:13rem", source)
        self.assertIn("Vis alle 13 Autonomi-trinn", source)
        self.assertIn("Siste levering</span>", source)

    def test_portfolio_needs_are_read_before_mission_creation(self):
        source = (Path(__file__).resolve().parents[1] / "market_intelligence.py").read_text(encoding="utf-8")
        self.assertLess(source.index("portfolio_need_preflight = read_portfolio_needs()"), source.index("create_investment_mission("))


if __name__ == "__main__":
    unittest.main()
