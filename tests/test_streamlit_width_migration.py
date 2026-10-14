from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
FILES=('ui_library/shell.py','preview_superfund.py','pages/superfund.py',
       'superfund_portfolio_overview.py','public_report_ui.py',
       'pages/super_portfolio.py','quality_valuation_ui.py',
       'superfund_presentation.py')

def test_deprecated_streamlit_width_arguments_removed():
    for file in FILES:
        text=(ROOT/file).read_text(encoding='utf-8')
        assert 'use_container_width=' not in text, file
        assert "width='stretch'" in text, file

def test_shared_table_wrapper_uses_new_width_api():
    text=(ROOT/'ui_library/tables.py').read_text(encoding='utf-8')
    assert '"width": "stretch" if use_container_width else "content"' in text
    assert '"use_container_width": use_container_width' not in text
