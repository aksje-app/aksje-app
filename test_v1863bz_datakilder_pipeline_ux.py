from pathlib import Path


ROOT = Path(__file__).resolve().parent


def test_kilder_og_import_lives_inside_ai_candidate_workspace():
    app = (ROOT / "app.py").read_text(encoding="utf-8")
    layout = (ROOT / "workspace_layout.py").read_text(encoding="utf-8")
    active_layout = layout[layout.index("def _render_ai_control_center_v1863aj") :]

    assert '("Kilder og import", render_analysis_pipeline_control_center_v1863bv)' not in app
    assert '("AI Kandidattest", render_ai_candidate_test_control_center_v1864l)' in app
    assert "#### Kilder og import" in app
    assert 'with st.expander("Kilder og import", expanded=True):' in app
    assert "Status for arbeidsflyten" not in app
    assert "Detaljer for valgt steg / send videre" not in app
    assert "Pakkevisning" not in app
    assert "Mottatt fra forrige test" not in app
    assert "Send valgt output videre" not in app
    assert "_render_pipeline_quick_start_v1863bx(panel_map, group_map)" not in active_layout
    assert "analysis_pipeline_shortcut_" not in active_layout
    assert "Ingen valgt" not in active_layout


def test_source_selector_renders_sources_without_separate_menu_pages():
    app = (ROOT / "app.py").read_text(encoding="utf-8")

    assert "source_options =" in app and "Folketrygdfondet" in app and "Akt" in app
    assert "ai_candidate_source_hub_choice_v1864q" in app
    assert "ai_candidate_source_hub_quick_" not in app
    assert "render_finansavisen_bjellesau_panel()" in app
    assert "render_nbim_radar_panel()" in app
    assert "render_folketrygdfondet_panel()" in app
    assert '_pipeline_go_to_panel_v1863by("AI Kandidattest", "Finansavisen Bjellesauer")' not in app
    assert '_pipeline_go_to_panel_v1863by("AI Kandidattest", "Oljefond Radar")' not in app
    assert '_pipeline_go_to_panel_v1863by("AI Kandidattest", "Folketrygdfondet")' not in app
    assert '("Oljefond Radar", render_nbim_radar_panel)' not in app
    assert '("Folketrygdfondet", render_folketrygdfondet_panel)' not in app
    assert '("Finansavisen Bjellesauer", render_finansavisen_bjellesau_panel)' not in app


def test_finansavisen_source_sends_to_ai_candidate_not_test2():
    finance_ui = (ROOT / "finansavisen_bjellesau_ui.py").read_text(encoding="utf-8")

    assert "Send valgte tickere til AI Kandidattest" in finance_ui
    assert "Send hele kildegrunnlaget til AI Kandidattest" in finance_ui
    assert "open_ai_candidate_test(tickers=matched_tickers" in finance_ui
    assert "Send valgte tickere til Test 2 Marked/rangering" not in finance_ui
    assert "Send hele dataunderlaget til Test 2 Marked/rangering" not in finance_ui
    assert '"stage_id": "market_ranking"' not in finance_ui


def test_folketrygdfondet_has_import_search_export_and_ai_candidate_actions():
    ui = (ROOT / "folketrygdfondet_ui.py").read_text(encoding="utf-8")
    source = (ROOT / "folketrygdfondet.py").read_text(encoding="utf-8")

    assert "Importer og lagre Folketrygdfondet" in ui
    assert "folketrygdfondet_search_v1864p" in ui
    assert "AI Kandidattest trenger matchede tickere" in ui
    assert "CSV" in ui and "JSON snapshot" in ui and "Print/PDF HTML" in ui and "Last ned PDF" in ui
    assert "Send valgte til AI Kandidattest" in ui
    assert "Send alle matchede til AI Kandidattest" in ui
    assert "folketrygdfondet_open_ai_candidate_source_v1864p" in ui
    assert "save_folketrygdfondet_overlay(overlay, parsed_rows, source_as_of=source_as_of" in ui
    assert "load_folketrygdfondet_snapshot" in source
    assert "build_folketrygdfondet_report_pdf" in source


def test_version_records_configurable_ai_candidate_engine():
    version = (ROOT / "app_version.py").read_text(encoding="utf-8")

    assert 'APP_VERSION = "v18.6.4v"' in version
    assert "Printable Technical Charts and Clean Detail Graphs" in version
    assert "Evalueringsoppsett er lagt inn i AI Kandidattest" in version





