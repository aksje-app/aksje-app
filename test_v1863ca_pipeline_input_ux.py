from pathlib import Path

from services.analysis_pipeline_service import stage_wizard_info


ROOT = Path(__file__).resolve().parent


def test_kilder_og_import_is_ai_candidate_source_hub():
    app = (ROOT / "app.py").read_text(encoding="utf-8")

    assert "Kilder og import" in app
    assert "AI Kandidattest henter bare relevant evidens" in app
    assert "Status for arbeidsflyten" not in app
    assert "Godkjenn dataunderlag og aapne Test 2" not in app


def test_finansavisen_sends_source_tickers_to_ai_candidate():
    ui = (ROOT / "finansavisen_bjellesau_ui.py").read_text(encoding="utf-8")

    assert "def _send_finansavisen_to_test2" in ui
    assert "Input Finansavisen" in ui
    assert "Klar til AI Kandidattest" in ui
    assert "Send valgte tickere til AI Kandidattest" in ui
    assert "Send hele kildegrunnlaget til AI Kandidattest" in ui
    assert '"stage_id": "market_ranking"' not in ui
    assert "Send til Beslutningsgrunnlag" in ui
    assert "max_selections=len(decision_options)" in ui


def test_marked_room_groups_market_tools_behind_toolbar():
    app = (ROOT / "app.py").read_text(encoding="utf-8")
    layout = (ROOT / "workspace_layout.py").read_text(encoding="utf-8")

    assert "def render_market_room_control_center_v1863cb" in app
    assert "def _render_market_room_toolbar_v1863cb" in app
    assert '("Marked", render_market_room_control_center_v1863cb)' in app
    assert '["Oversikt", "Rangering", "Heatmap", "Markedsklima", "Lagrede signaler", "IPO", "Regime", "Makro", "Nyheter"]' in app
    assert '["Sektor", "Land", "Industri", "Faktorstil", "Risikostil", "Storrelse"]' in app
    assert "render_market_ranking_control_center_v18535(selected_market=" in app
    assert '"market_ranking": ("marked",)' in layout
    assert "Varsler og watchlist" in app


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
    assert "Fortsett med raa input fra Test 2" in analysis


def test_folketrygdfondet_is_source_overlay_not_pipeline_payload():
    app = (ROOT / "app.py").read_text(encoding="utf-8")
    ui = (ROOT / "folketrygdfondet_ui.py").read_text(encoding="utf-8")
    source = (ROOT / "folketrygdfondet.py").read_text(encoding="utf-8")

    assert "Folketrygdfondet" in app
    assert "render_folketrygdfondet_panel" in app
    assert "Importer Folketrygdfondet XLS" in ui
    assert "AI Kandidattest kan bruke som kildeevidens" in ui
    assert "read_folketrygdfondet_xls_bytes" in source
    assert "build_folketrygdfondet_overlay" in source
    assert "save_folketrygdfondet_overlay(overlay, parsed_rows, source_as_of=source_as_of" in ui
    requirements = (ROOT / "requirements.txt").read_text(encoding="utf-8")
    assert "xlrd" in requirements
    assert "openpyxl" in requirements


def test_analysis_pipeline_ticker_extraction_does_not_read_metadata_keys():
    from services.universe_service import _extract_tickers

    rows = [
        {
            "ticker": "PEXIP.OL",
            "name": "Pexip",
            "raw": {"RAW": {"ticker": "SHOULDNOT.OL"}, "SCORE_PARTS": {"value": 1}},
            "score_parts": {"momentum": 70},
        },
        {"ticker": "RAW", "name": "metadata token"},
        {"ticker": "SCORE_PARTS", "name": "metadata token"},
        {"ticker": "MANGLERDIREKTEEVIDENS", "name": "metadata token"},
        {"DNB.OL": {"qty": 1}},
    ]

    assert _extract_tickers(rows) == ["PEXIP.OL", "DNB.OL"]


def test_known_us_names_are_resolved_in_quick_cards():
    metadata = (ROOT / "security_metadata.py").read_text(encoding="utf-8")

    assert '"MO": {"name": "Altria Group, Inc."' in metadata
    assert '"AKAM": {"name": "Akamai Technologies, Inc."' in metadata








