from pathlib import Path

from services.analysis_pipeline_service import stage_wizard_info


ROOT = Path(__file__).resolve().parent


def test_test2_uses_dataunderlag_as_explicit_default_universe():
    defaults = stage_wizard_info("market_ranking")["defaults"]
    app = (ROOT / "app.py").read_text(encoding="utf-8")

    assert defaults["cc_ranking_market_v18535"] == "Dataunderlag"
    assert '"Dataunderlag"] + market_scope_options' in app
    assert "Input fra 1. Dataunderlag er mottatt" in app
    assert "Dataunderlag-universet bruker felles tickerunivers" in app
    assert "Bruker input fra 1. Dataunderlag" in app


def test_finansavisen_can_return_to_dataunderlag_before_test8_shortcut():
    ui = (ROOT / "finansavisen_bjellesau_ui.py").read_text(encoding="utf-8")

    assert "def _send_finansavisen_to_dataunderlag" in ui
    assert "Send til 1. Dataunderlag" in ui
    assert '"panel": "1. Dataunderlag"' in ui
    assert "Send direkte til Test 8 Beslutningsgrunnlag" in ui


def test_marked_room_groups_market_tools_behind_toolbar():
    app = (ROOT / "app.py").read_text(encoding="utf-8")
    layout = (ROOT / "workspace_layout.py").read_text(encoding="utf-8")

    assert "def render_market_room_control_center_v1863cb" in app
    assert "def _render_market_room_toolbar_v1863cb" in app
    assert '("Marked", render_market_room_control_center_v1863cb)' in app
    assert '["Oversikt", "Rangering", "Heatmap", "Regime", "Makro", "Nyheter"]' in app
    assert '["Sektor", "Land", "Industri", "Faktorstil", "Risikostil", "Storrelse"]' in app
    assert "render_market_ranking_control_center_v18535(selected_market=" in app
    assert '"marked", "marked/rangering"' in layout
