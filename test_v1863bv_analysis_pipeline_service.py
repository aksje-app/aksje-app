from pathlib import Path

import pytest

from services.analysis_pipeline_service import (
    ANALYSIS_PIPELINE_VERSION,
    get_analysis_pipeline_service,
    next_stage_id,
    normalize_candidate_rows,
    stage_wizard_info,
    standard_report_outline,
)
from services.state_service import StateService
from services.storage_service import StorageService


ROOT = Path(__file__).resolve().parent


def _service(tmp_path):
    return get_analysis_pipeline_service(
        state_service=StateService({}),
        storage_service=StorageService(base_dir=str(tmp_path / "services")),
    )


def test_pipeline_saves_output_and_next_input_without_autorun(tmp_path):
    service = _service(tmp_path)
    rows = [
        {"ticker": "EQNR.OL", "name": "Equinor", "score": 8.1, "source": "Marked"},
        {"ticker": "DNB.OL", "name": "DNB", "shared_score": 72, "source": "Marked"},
        {"ticker": "EQNR.OL", "name": "Duplicate", "score": 9.9, "source": "Marked"},
    ]

    result = service.save_stage_output("market_ranking", rows, source_label="Norge", auto_handoff=True)

    assert result.ok is True
    output = result.data["output_package"]
    handoff = result.data["handoff_package"]
    assert output["version"] == ANALYSIS_PIPELINE_VERSION
    assert output["stage_id"] == "market_ranking"
    assert output["package_type"] == "output"
    assert output["candidate_count"] == 2
    assert output["auto_run"] is False
    assert handoff["stage_id"] == "smart_ai"
    assert handoff["package_type"] == "input"
    assert handoff["status"] == "ready_for_stage"
    assert handoff["auto_run"] is False

    loaded_input = service.load_stage_input("smart_ai")
    assert loaded_input["candidate_count"] == 2
    assert loaded_input["source_package_id"] == output["package_id"]


def test_pipeline_status_and_manual_handoff(tmp_path):
    service = _service(tmp_path)
    service.save_stage_output("top_picks", [{"ticker": "STB.OL", "score": 6.7}], auto_handoff=False)

    before = service.load_stage_input("early_warning")
    assert before == {}

    handoff = service.handoff_latest_output_to_next("top_picks")

    assert handoff.ok is True
    after = service.load_stage_input("early_warning")
    assert after["candidate_count"] == 1
    statuses = {row["stage_id"]: row for row in service.stage_status()}
    assert statuses["top_picks"]["status"] == "ferdig"
    assert statuses["early_warning"]["status"] == "klar til kjoring"


def test_candidate_normalization_and_report_outline():
    rows = normalize_candidate_rows(
        {
            "ranked": [
                {"candidate": {"ticker": "  aapl ", "name": "Apple"}, "shared_score": 80, "recommended_action": "Analyser videre"},
                {"symbol": "MSFT", "decision_quality": 91, "company": "Microsoft"},
            ]
        },
        source_stage_id="auto_test_lab",
        source_label="Auto Test Lab",
    )

    assert [row["ticker"] for row in rows] == ["MSFT", "AAPL"]
    assert rows[0]["score"] == 91
    assert rows[1]["recommended_action"] == "Analyser videre"
    outline = standard_report_outline("early_warning")
    assert "Sammendrag" in outline
    assert any("Stegfokus" in line and "insider/bjellesau" in line for line in outline)
    assert next_stage_id("decision_support") == "portfolio_analysis"


def test_unknown_stage_is_rejected(tmp_path):
    service = _service(tmp_path)

    with pytest.raises(ValueError):
        service.save_stage_output("ikke_et_steg", [{"ticker": "ABC"}])


def test_pipeline_service_has_no_heavy_runtime_dependencies():
    source = (ROOT / "services" / "analysis_pipeline_service.py").read_text(encoding="utf-8")

    blocked = ["streamlit", "yfinance", "requests", "score_stock", "auto_rank_market", "run_auto_test_lab"]
    for term in blocked:
        assert term not in source


def test_pipeline_ui_and_panels_expose_handoff_without_hidden_run():
    app_source = (ROOT / "app.py").read_text(encoding="utf-8", errors="replace")
    decision_source = (ROOT / "decision_ui.py").read_text(encoding="utf-8", errors="replace")
    alpha_source = (ROOT / "alpha_radar_ui.py").read_text(encoding="utf-8", errors="replace")

    assert "def render_analysis_pipeline_control_center_v1863bv" in app_source
    assert "(\"1. Dataunderlag\", render_analysis_pipeline_control_center_v1863bv)" in app_source
    assert "Analyseflyt input" in app_source
    assert "Send valgt output videre og aapne neste test" in app_source
    assert "Input / output" in app_source
    assert "Aapne {info.get('test_label')} med standardvalg" not in app_source
    assert "Hent fra analyseflyt" in decision_source
    assert ".save_stage_output(" in alpha_source
    assert "auto_run" in (ROOT / "services" / "analysis_pipeline_service.py").read_text(encoding="utf-8")


def test_pipeline_wizard_numbers_defaults_and_navigation_are_static():
    app_source = (ROOT / "app.py").read_text(encoding="utf-8", errors="replace")
    smart_source = (ROOT / "analysis_universe_ai.py").read_text(encoding="utf-8", errors="replace")
    decision_source = (ROOT / "decision_ui.py").read_text(encoding="utf-8", errors="replace")
    layout_source = (ROOT / "workspace_layout.py").read_text(encoding="utf-8", errors="replace")
    service_source = (ROOT / "services" / "analysis_pipeline_service.py").read_text(encoding="utf-8")

    assert stage_wizard_info("data_foundation")["wizard_label"] == "Steg 1 av 10: Dataunderlag"
    assert stage_wizard_info("paper_trading")["wizard_label"] == "Test 10 av 10: Paper Trading"
    assert stage_wizard_info("top_picks")["defaults"]["cc_top_picks_scope_v1863s"] == "Analyseflyt input"
    assert stage_wizard_info("early_warning")["defaults"]["alpha_radar_engine_v1863au"] == "Early Warning V1"
    assert stage_wizard_info("auto_test_lab")["defaults"]["auto_lab_scope_v18537"] == "Analyseflyt input"
    assert stage_wizard_info("portfolio_analysis")["defaults"]["mixed_portfolio_stock_source_v18544"] == "Analyseflyt input"

    assert "analysis_pipeline_pending_nav_v1863bw" in layout_source
    assert "dataunderlag" in layout_source.lower()
    assert "_render_pipeline_stage_bar_v1863bw(\"market_ranking\")" in app_source
    assert "_render_pipeline_stage_bar_v1863bw(\"top_picks\")" in app_source
    assert "_render_pipeline_stage_bar_v1863bw(\"auto_test_lab\")" in app_source
    assert "_render_pipeline_stage_bar_v1863bw(\"portfolio_analysis\")" in app_source
    assert "_render_pipeline_stage_bar_v1863bw(\"paper_trading\")" in app_source
    assert "smart_ai_pipeline_next_v1863bw" in smart_source
    assert "decision_pipeline_next_v1863bw" in decision_source
    assert "Send output til Test" in app_source
    assert "PIPELINE_PENDING_NAV_KEY" in service_source
