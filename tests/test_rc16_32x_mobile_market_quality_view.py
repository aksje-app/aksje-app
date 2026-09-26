from pathlib import Path

from app_version import APP_VERSION, APP_VERSION_NAME, PREVIOUS_APP_VERSION
from navigation_state import canonical_nav_for_panel_v19220_rc7
from ui_library.shell import render_shell


ROOT = Path(__file__).resolve().parents[1]


class _MarkdownRecorder:
    def __init__(self):
        self.blocks: list[str] = []

    def markdown(self, value, **_kwargs):
        self.blocks.append(str(value))


def test_release_identity_for_mobile_market_quality_view():
    assert APP_VERSION == "v19.22.0-rc16.32x"
    assert PREVIOUS_APP_VERSION == "v19.22.0-rc16.32w"
    assert "Mobile Market Quality View" in APP_VERSION_NAME


def test_mobile_market_link_targets_market_scanner_route():
    recorder = _MarkdownRecorder()
    assert render_shell(recorder, "market") == "market"
    html = "\n".join(recorder.blocks)
    assert '?aa_nav=market' in html
    assert '?aa_nav=long_engine' not in html
    assert canonical_nav_for_panel_v19220_rc7(
        "Marked og signaler", "🔍 Marked – Market Scanner"
    ) == "market"


def test_market_toolbar_is_mobile_safe_and_quality_is_a_first_class_view():
    source = (ROOT / "app.py").read_text(encoding="utf-8")
    start = source.index("def _render_market_room_toolbar_v1863cb")
    end = source.index("def _render_market_room_overview_v1863cb", start)
    toolbar = source[start:end]

    assert 'view = st.selectbox(\n        "Visning"' in toolbar
    assert '"Kvalitet og prising"' in toolbar
    assert "st.columns([0.42" not in toolbar
    assert 'with st.expander("Diagram og filtre"' in toolbar
    assert 'render_quality_valuation(st, quality_tickers, expanded=True)' in source


def test_quality_panel_can_be_opened_directly():
    source = (ROOT / "quality_valuation_ui.py").read_text(encoding="utf-8")
    assert "*, expanded: bool = False" in source
    assert 'expanded=expanded' in source
