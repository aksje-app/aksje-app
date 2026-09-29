from pathlib import Path
import app_version

ROOT = Path(__file__).resolve().parents[1]
PAGE = ROOT / 'pages' / 'super_portfolio.py'


def test_rc16_32g_remains_in_changelog_after_later_releases():
    assert any(str(row).startswith('v19.22.0-rc16.32g:') for row in app_version.CHANGELOG)


def test_manual_evaluation_uses_durable_single_job_guard_and_progress():
    src = PAGE.read_text(encoding='utf-8')
    assert 'start_job("MANUAL", True)' in src
    assert 'ACTIVE_STATES' in src
    assert '_render_sp_job_progress' in src
    assert 'run_every="5s"' in src
    assert 'SP jobbdiagnose' in src


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
