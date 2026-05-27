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

    assert "Start her: 1. Dataunderlag" in layout
    assert "analysis_pipeline_shortcut_" in layout
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
    assert "Forrige:" in app
    assert 'pipeline.save_stage_output(\n                "data_foundation"' in app
    assert "auto_handoff=True" in app
    assert "Detaljer for valgt steg / send videre" in app
    assert "Send valgt output videre og aapne neste test" in app
    assert "Send siste output videre og aapne neste test" not in app
    assert "Aapne {info.get('test_label')} med standardvalg" not in app
    assert 'status_df[["nr", "steg", "status", "input", "output", "neste"]]' not in app


def test_version_records_datakilder_pipeline_shortcuts():
    version = (ROOT / "app_version.py").read_text(encoding="utf-8")

    assert 'APP_VERSION = "v18.6.4e"' in version
    assert "Dynamic Slider Guard" in version
    assert "hurtigtaster for Test 1-10" in version




