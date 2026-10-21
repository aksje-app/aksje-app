from pathlib import Path
import ast
ROOT=Path(__file__).resolve().parents[1]

def test_mobile_research_sources_compile():
    for path in ("research_findings_dashboard.py","strategy_history_progress_view.py","pages/autonomy.py","ui/global_styles.py"):
        ast.parse((ROOT/path).read_text(encoding="utf-8"), filename=path)

def test_plain_language_and_mobile_css():
    findings=(ROOT/"research_findings_dashboard.py").read_text(encoding="utf-8")
    assert "Hva viser aksjetestene så langt?" in findings
    assert "Typisk resultat i kontrollperioden" in findings
    assert "Grense for tap" in findings
    styles=(ROOT/"ui/global_styles.py").read_text(encoding="utf-8")
    assert "_inject_research_mobile_readability_v1()" in styles
    assert "line-height:1.5" in styles

def test_autonomy_no_cramped_core_metric_grid():
    source=(ROOT/"pages/autonomy.py").read_text(encoding="utf-8")
    assert 'with st.expander("Teknisk systemstatus"' in source
