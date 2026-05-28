from pathlib import Path

from services.analysis_pipeline_service import stage_wizard_info


ROOT = Path(__file__).resolve().parent


def test_test2_uses_dataunderlag_as_explicit_default_universe():
    defaults = stage_wizard_info("market_ranking")["defaults"]
    app = (ROOT / "app.py").read_text(encoding="utf-8")

    assert defaults["cc_ranking_market_v18535"] == "Dataunderlag"
    assert '"Dataunderlag"] + market_scope_options' in app
    assert "Input fra 1. Dataunderlag er mottatt" in app
    assert "Test 2 bruker denne inputpakken" in app
    assert "source_tickers = (data_foundation_tickers or get_all_tickers())[: int(limit)]" in app
    assert "Bruker input fra 1. Dataunderlag" in app


def test_finansavisen_sends_dataunderlag_to_test2_before_test8_shortcut():
    ui = (ROOT / "finansavisen_bjellesau_ui.py").read_text(encoding="utf-8")

    assert "def _send_finansavisen_to_test2" in ui
    assert "Input Finansavisen" in ui
    assert "Output til Test 2" in ui
    assert "Send valgte tickere til Test 2 Marked/rangering" in ui
    assert "Send hele dataunderlaget til Test 2 Marked/rangering" in ui
    assert '"stage_id": "market_ranking"' in ui
    assert "Send direkte til Test 8 Beslutningsgrunnlag" in ui
    assert "max_selections=len(decision_options)" in ui


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


def test_test3_to_10_prefer_analysis_pipeline_input_and_specific_send_labels():
    app = (ROOT / "app.py").read_text(encoding="utf-8")
    analysis = (ROOT / "analysis_universe_ai.py").read_text(encoding="utf-8")
    service = (ROOT / "services" / "analysis_pipeline_service.py").read_text(encoding="utf-8")
    universe = (ROOT / "services" / "universe_service.py").read_text(encoding="utf-8")

    assert '"smart_ai": {' in service
    assert '"ai_universe_mode_draft_v1853": "Analyseflyt input"' in service
    assert '"Analyseflyt input"' in analysis
    assert 'current["mode"] = "Analyseflyt input"' in analysis
    assert 'mode == "Analyseflyt input" or "Analyseflyt input" in scopes' in universe
    assert "Send {output_count} {noun} til Test" in app or "Send {output_count} kandidater til Test" in app
    assert "Test 2 kjører" in app or "Test 2 kjÃ¸rer" in app
    assert "kandidater klare for Test 3" in app


def test_known_us_names_are_resolved_in_quick_cards():
    metadata = (ROOT / "security_metadata.py").read_text(encoding="utf-8")

    assert '"MO": {"name": "Altria Group, Inc."' in metadata
    assert '"AKAM": {"name": "Akamai Technologies, Inc."' in metadata


