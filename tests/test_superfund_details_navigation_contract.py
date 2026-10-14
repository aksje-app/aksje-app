"""Static release contracts for the shared fund-analysis navigation and exports."""
from pathlib import Path

def test_fund_detail_navigation_and_exports_contract():
    page=Path("pages/superfund.py").read_text(encoding="utf-8")
    reports=Path("superfund_reports.py").read_text(encoding="utf-8")
    presentation=Path("superfund_presentation.py").read_text(encoding="utf-8")
    assert "st.session_state['sf_selected_fund']=rank_row['id']" in page
    assert "st.session_state.pop('sf_selected_fund',None)" in page
    assert "sf_owned_sort" in page
    assert "fund_pdf_bytes(s,selected)" in page
    assert "def fund_pdf_bytes(" in reports
    for choice in ("'1 dag'","'1 uke'","'1 måned'","'Så langt i år'","'1 år'","'3 år'","'5 år'"):
        assert choice in presentation

def test_diagnostic_score_evidence_is_exported():
    diagnostic=Path("superfund_diagnostics.py").read_text(encoding="utf-8")
    assert "owned_ranking_controls.json" in diagnostic
    assert "missing_scores" in diagnostic
