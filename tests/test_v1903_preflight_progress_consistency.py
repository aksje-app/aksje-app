from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]


class PreflightProgressConsistencyTests(unittest.TestCase):
    def test_legacy_mission_is_saved_before_versioned_contract(self):
        source = (ROOT / "autonomy_modes.py").read_text(encoding="utf-8")
        block = source[source.index("if submitted:"):source.index("if is_running(status):")]
        self.assertLess(block.index("saved = save_user_mission"), block.index("contract = create_investment_mission"))

    def test_previous_success_is_not_shown_as_current_failed_execution(self):
        source = (ROOT / "autonomy_overview.py").read_text(encoding="utf-8")
        self.assertIn('str(status.get("state") or "") == "COMPLETED"', source)
        self.assertIn('current_result_id == latest_result_id', source)

    def test_live_panel_states_automatic_refresh_interval(self):
        source = (ROOT / "autonomy_overview.py").read_text(encoding="utf-8")
        self.assertIn('fragment(run_every="3s")', source)
        self.assertIn("oppdateres automatisk hvert 3. sekund", source)


if __name__ == "__main__":
    unittest.main()
