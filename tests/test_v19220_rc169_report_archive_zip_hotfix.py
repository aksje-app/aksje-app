from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_empty_projected_ranking_never_creates_zero_streamlit_columns():
    source = (ROOT / "market_intelligence.py").read_text(encoding="utf-8")
    assert "st.columns(min(3, len(displayed_candidates))) if displayed_candidates else []" in source
    assert "Ingen kandidater er rangert for prioritert oppfølging" in source


def test_all_reports_zip_is_available_in_report_archive():
    source = (ROOT / "market_intelligence.py").read_text(encoding="utf-8")
    archive_start = source.index('with tab_reports:')
    archive_end = source.index('with tab_accuracy:', archive_start)
    archive_panel = source[archive_start:archive_end]
    assert "Last ned alle rapporter samlet" in archive_panel
    assert "Bygg samlet ZIP av alle rapporter" in archive_panel
    assert "start_replay_export()" in archive_panel
    assert "_replay_export_status_fragment_v19220_rc16()" in archive_panel


def test_release_contract_identifies_rc169_hotfix():
    source = (ROOT / "app_version.py").read_text(encoding="utf-8")
    assert 'APP_VERSION = "v19.22.0-rc16.9"' in source
    assert "st.columns(0)" in source
