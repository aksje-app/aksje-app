from pathlib import Path

from ui_library.shell import render_shell

ROOT = Path(__file__).resolve().parents[1]

class Recorder:
    def __init__(self):
        self.blocks = []
    def markdown(self, value, **_kwargs):
        self.blocks.append(str(value))

def test_direct_quality_menu_link_is_rendered():
    recorder = Recorder()
    assert render_shell(recorder, "quality_valuation") == "quality"
    html = "\n".join(recorder.blocks)
    assert html.count("?aa_nav=quality_valuation") >= 2
    assert "Kvalitet" in html

def test_direct_quality_route_preselects_quality_view():
    source = (ROOT / "app.py").read_text(encoding="utf-8")
    assert 'nav in {"market", "quality_valuation"}' in source
    assert 'if nav == "quality_valuation":' in source
    assert 'st.session_state["market_room_view_v1863cb"] = "Kvalitet og prising"' in source
