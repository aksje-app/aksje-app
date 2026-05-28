from pathlib import Path

from services.analysis_pipeline_service import stage_wizard_info, standard_report_outline


ROOT = Path(__file__).resolve().parent


def test_datakilder_is_the_first_pipeline_stage_name():
    info = stage_wizard_info("data_foundation")

    assert info["wizard_label"] == "Steg 1 av 10: Dataunderlag"
    assert info["panel_label"] == "1. Dataunderlag"
    assert "Ingen analyse kjoeres her" in info["purpose"]
    assert standard_report_outline("data_foundation")[3].startswith("Stegfokus: dataunderlag")


def test_control_center_has_clickable_pipeline_shortcuts_and_synced_active_stage():
    layout = (ROOT / "workspace_layout.py").read_text(encoding="utf-8")

    assert "Start her: 1. Dataunderlag" not in layout
    assert "analysis_pipeline_shortcut_" in layout
    assert "analysis_pipeline_shortcut_{stage_id}_v1863bz" in layout
    assert "analysis_pipeline_active_stage_v1863bz" in layout
    assert "pending_nav_sync" in layout
    assert "ai_control_center_panel_radio_v1863aj_" in layout
    assert "stage_wizard_info_func" in layout


def test_pipeline_package_view_explains_input_output_and_datakilder_report():
    app = (ROOT / "app.py").read_text(encoding="utf-8")

    assert "Input fra forrige steg" in app
    assert "Output fra dette steg" in app
    assert "Kontrollrapport klar" in app
    assert "Output fra dette steg" in app
    assert "def _render_data_foundation_package_v1863bz" in app
    assert "Dataunderlag sender et kontrollpunkt videre, ikke en aksjeliste" in app
    assert "Godkjenn dataunderlag og aapne Test 2" in app
    assert "raa importfiler sendes ikke gjennom Test 1-10" in app
    assert "Importer Folketrygdfondet XLS" in app
    assert "Forrige:" in app
    assert 'pipeline.save_stage_output(\n                "data_foundation"' in app
    assert "auto_handoff=True" in app
    assert "Detaljer for valgt steg / send videre" in app
    assert "Send valgt output videre og aapne neste test" in app
    assert "Send siste output videre og aapne neste test" not in app
    assert "Aapne {info.get('test_label')} med standardvalg" not in app
    assert 'status_df[["nr", "steg", "status", "input", "output", "neste"]]' not in app


def test_finansavisen_dataunderlag_sends_to_test2_not_same_stage():
    finance_ui = (ROOT / "finansavisen_bjellesau_ui.py").read_text(encoding="utf-8")
    app = (ROOT / "app.py").read_text(encoding="utf-8")

    assert "Input Finansavisen" in finance_ui
    assert "Output til Test 2" in finance_ui
    assert "Send valgte tickere til Test 2 Marked/rangering" in finance_ui
    assert "Send hele dataunderlaget til Test 2 Marked/rangering" in finance_ui
    assert "stage_wizard_info(\"market_ranking\")" in finance_ui
    assert '"stage_id": "market_ranking"' in finance_ui
    assert "finansavisen_bjellesau_send_dataunderlag_v1863ca" not in finance_ui
    assert "finansavisen_bjellesau_send_selected_test2_v1864i" in finance_ui
    assert "finansavisen_bjellesau_send_all_test2_v1864i" in finance_ui
    assert "Send til 1. Dataunderlag" not in finance_ui
    assert "data_foundation_tickers" in app
    assert "source_tickers = (data_foundation_tickers or get_all_tickers())[: int(limit)]" in app


def test_finansavisen_import_uses_one_actor_sync_control():
    finance_ui = (ROOT / "finansavisen_bjellesau_ui.py").read_text(encoding="utf-8")

    assert "Oppdater Aktorregister fra import" in finance_ui
    assert "sync_finansavisen_actors_to_registry(merged)" in finance_ui
    assert "Synk lagret import til Aktorregister" not in finance_ui
    assert "finansavisen_bjellesau_sync_saved" not in finance_ui


def test_version_records_datakilder_pipeline_shortcuts():
    version = (ROOT / "app_version.py").read_text(encoding="utf-8")

    assert 'APP_VERSION = "v18.6.4n"' in version
    assert "AI Candidate Hub" in version
    assert "Folketrygdfondet har nytt importpanel" in version







