from pathlib import Path


def test_app_version_is_single_source_for_topbar_and_universe_service():
    version = Path("app_version.py").read_text(encoding="utf-8")
    sticky = Path("sticky_topbar.py").read_text(encoding="utf-8")
    universe_service = Path("services/universe_service.py").read_text(encoding="utf-8")

    assert 'APP_VERSION = "v18.5.28"' in version
    assert "get_app_version()" in sticky
    assert "get_app_version()" in universe_service
    assert "Professional Trading Workspace v18.4.7" not in sticky


def test_smart_universe_uses_dark_html_tables_not_native_dataframe_boxes():
    source = Path("analysis_universe_ai.py").read_text(encoding="utf-8")

    assert "def _render_dark_table" in source
    assert "ai-universe-table-wrap" in source
    assert "st.dataframe" not in source
