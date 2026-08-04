from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_reports_follows_overview_in_workspace_menu():
    source = (ROOT / 'navigation_state.py').read_text(encoding='utf-8')
    assert source.index('"overview": "Oversikt"') < source.index('"reports": "Rapporter"') < source.index('"orchestrator": "Orkestrering og tidsplan"')


def test_report_center_sections_follow_agreed_operator_workflow():
    source = (ROOT / 'market_intelligence.py').read_text(encoding='utf-8')
    headings = [
        '##### 1. Status for planlagte rapporter',
        '##### 2. Handlinger',
        '##### 3. Siste rapporter',
        '##### 4. Historikk',
        '5. Planlegging og avanserte innstillinger',
    ]
    positions = [source.index(heading) for heading in headings]
    assert positions == sorted(positions)
    assert 'st.tabs(["Jobbprofiler", "Siste rapport", "Rapporter"' not in source


def test_compact_report_actions_include_night_and_do_not_stretch():
    source = (ROOT / 'market_intelligence.py').read_text(encoding='utf-8')
    for label in ['📄 Nytt utkast', '🌅 Kjør morgenanalyse', '🌇 Kjør kveldsanalyse', '🌙 Kjør nattanalyse']:
        assert label in source
    action_start = source.index('##### 2. Handlinger')
    action_end = source.index('##### 3. Siste rapporter')
    action_block = source[action_start:action_end]
    assert action_block.count('width="content"') >= 4
    assert 'width="stretch"' not in action_block


def test_missed_report_action_is_compact_and_unique():
    source = (ROOT / 'market_intelligence.py').read_text(encoding='utf-8')
    assert source.count('key=f"mi_catchup_{job.job_id}"') == 1
    assert 'missed_action.button("Kjør manglende rapport nå"' in source
    status_start = source.index('##### 1. Status for planlagte rapporter')
    actions_start = source.index('##### 2. Handlinger')
    assert 'width="content"' in source[status_start:actions_start]


def test_advanced_job_settings_are_collapsed_and_checkbox_groups_are_framed():
    source = (ROOT / 'market_intelligence.py').read_text(encoding='utf-8')
    assert 'with st.expander("5. Planlegging og avanserte innstillinger", expanded=False):' in source
    settings_start = source.index('##### Varsling, lagring og aktivering')
    settings_end = source.index('##### Etter skanningen')
    settings_block = source[settings_start:settings_end]
    assert 'with st.container(border=True):' in settings_block
    for label in ['Send med Pushover', 'Lagre PDF', 'Aktiv jobb', 'Direkte lenke til PDF', 'Top 3 i varsel']:
        assert label in settings_block


def test_investor_edition_branding_and_version():
    version = (ROOT / 'app_version.py').read_text(encoding='utf-8')
    report = (ROOT / 'market_intelligence.py').read_text(encoding='utf-8')
    assert 'APP_VERSION = "v19.22.0-rc7"' in version
    assert 'Investor Edition' in report


def test_distribution_tools_follow_canonical_release():
    from app_version import APP_VERSION
    from tools.build_safe_distribution import VERSION as BUILD_VERSION
    from tools.validate_distribution import EXPECTED_VERSION
    assert BUILD_VERSION == APP_VERSION
    assert EXPECTED_VERSION == APP_VERSION
