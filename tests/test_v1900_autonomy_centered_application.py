import unittest
from pathlib import Path
from unittest.mock import patch

from autonomi_core.configuration.application_centered import application_navigation, compatibility_manifest, request_activation, shadow_readiness


def records(count=3, valid=True):
    return [{"validation_id": f"PV-{i}", "authority_preserved": valid, "mode": "SHADOW_READ_ONLY", "writes_blocked": ["TOP_PICKS"]} for i in range(count)]


class AutonomyCenteredApplicationTests(unittest.TestCase):
    def test_final_navigation_is_exact(self):
        self.assertEqual(
            [x[1] for x in application_navigation()],
            ["Dashboard", "Autonomi", "Analyse", "Top Picks", "Paper Trading", "Portefølje", "Rapporter", "System"],
        )

    def test_shadow_gate_blocks_early_activation(self):
        self.assertFalse(shadow_readiness(records(2))["ready"])
        self.assertFalse(shadow_readiness(records(3, valid=False))["ready"])

    @patch("autonomi_core.runtime.parallel_validation.load_parallel_validation_history", return_value=records(3))
    @patch("autonomi_core.configuration.registry.propose", return_value={"approval_id": "CAP-V19", "status": "PENDING"})
    def test_activation_always_enters_explicit_approval_queue(self, propose, _history):
        result = request_activation()
        self.assertEqual(result["status"], "PENDING")
        propose.assert_called_once()

    def test_legacy_is_hidden_not_deleted_and_rollback_exists(self):
        manifest = compatibility_manifest()
        self.assertFalse(manifest["legacy_deleted"])
        self.assertEqual(manifest["legacy_mode"], "EXPERT_DIAGNOSTICS")
        self.assertTrue(manifest["rollback"])

    def test_routes_and_other_panels_gate_are_present(self):
        root = Path(__file__).resolve().parents[1]
        sidebar = (root / "ui_sidebar_stable.py").read_text(encoding="utf-8")
        workspace = (root / "workspace_layout.py").read_text(encoding="utf-8")
        app = (root / "app.py").read_text(encoding="utf-8")
        self.assertIn('nav in {"portfolio", "reports"}', sidebar)
        self.assertIn("if extra_labels and not _autonomy_centered_v1900()", workspace)
        self.assertIn('st.session_state["cc_top_picks_scope_v1863s"] = canonical_label', app)
        self.assertIn('"operations": "Varsler og drift"', app)
        self.assertIn('"engine_details": "Motorresultater"', app)


if __name__ == "__main__": unittest.main()
