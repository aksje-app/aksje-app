from pathlib import Path
import ast

ROOT=Path(__file__).resolve().parents[1]

def test_quality_ui_parses_and_uses_native_return_navigation():
    source=(ROOT/"quality_valuation_ui.py").read_text(encoding="utf-8")
    ast.parse(source)
    assert 'st.button("← Tilbake til Marked"' in source
    assert 'st.query_params["aa_nav"] = "market"' in source
    assert 'st.session_state["market_room_view_v1863cb"] = "Market Scanner"' in source
    assert 'st.rerun()' in source
    assert 'st.link_button("← Tilbake til programmet"' not in source

def test_quality_mobile_rows_are_isolated_and_warning_is_explicit():
    source=(ROOT/"quality_valuation_ui.py").read_text(encoding="utf-8")
    assert "with st.container(border=True):" in source
    assert "Pushover: IKKE SENDT" in source
    assert 'st.markdown("\\n".join(f"- ⚠️ {warning}"' in source
