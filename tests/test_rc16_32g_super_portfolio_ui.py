from pathlib import Path
import app_version

ROOT = Path(__file__).resolve().parents[1]
PAGE = ROOT / 'pages' / 'super_portfolio.py'


def test_version_contract_is_rc16_32g():
    assert app_version.APP_VERSION == 'v19.22.0-rc16.32g'
    assert app_version.PREVIOUS_APP_VERSION == 'v19.22.0-rc16.32f'


def test_manual_evaluation_button_has_single_run_guard_and_progress_bar():
    src = PAGE.read_text(encoding='utf-8')
    assert 'sp_evaluation_running' in src
    assert 'disabled=evaluation_running' in src
    assert 'st.progress(' in src
    assert '⏳ Jobber' in src
    assert 'finally:' in src


def test_dense_super_portfolio_sections_are_horizontal_and_collapsible():
    src = PAGE.read_text(encoding='utf-8')
    assert 'info_row_1 = st.columns(3)' in src
    assert 'info_row_2 = st.columns(3)' in src
    for title in (
        '🧠 Hvorfor er aksjene med?',
        '🕒 Data Freshness',
        '📅 Event Risk',
        '🛡️ Stop Pressure',
        '🚀 Ranking Velocity',
        '💭 AI WOULD DO TODAY',
    ):
        assert f'st.expander("{title}"' in src


def test_dense_sections_use_tables_instead_of_long_write_lines():
    src = PAGE.read_text(encoding='utf-8')
    assert 'why_rows' in src
    assert 'freshness_rows' in src
    assert 'stop_rows' in src
    assert 'velocity_rows' in src
    assert 'advisory_rows' in src
