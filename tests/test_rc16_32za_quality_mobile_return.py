from pathlib import Path
import ast

ROOT=Path(__file__).resolve().parents[1]

def test_quality_ui_parses_and_uses_native_return_navigation():
    from public_report_ui import _absolute_report_return_url
    url = _absolute_report_return_url('quality_reports', 'quality_valuation/runs/TEST')
    assert 'aa_nav=quality_valuation' in url and 'qv_reports=1' in url
    source=(ROOT/'quality_valuation_ui.py').read_text(encoding='utf-8')
    ast.parse(source)
    assert 'Tilbake til Kvalitet' in source
    assert 'aa_nav=quality_valuation' in source

def test_quality_mobile_rows_are_isolated_and_warning_is_explicit():
    source=(ROOT/"quality_valuation_ui.py").read_text(encoding="utf-8")
    assert "with st.container(border=True):" in source
    assert "Pushover: IKKE SENDT" in source
    assert '_warning_kind(str(warning))' in source
    assert 'for warning in warnings:' in source

def test_overview_has_direct_quality_quick_action():
    source=(ROOT/"pages"/"overview.py").read_text(encoding="utf-8")
    ast.parse(source)
    assert '("Kjør kvalitetsvurdering", "quality_valuation", "aa_overview_quality")' in source
    assert 'type="primary" if route == "quality_valuation"' in source
