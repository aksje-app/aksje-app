from pathlib import Path


def test_reports_follows_overview_in_workspace_menu():
    source = Path('pages/autonomy.py').read_text(encoding='utf-8')
    assert source.index('"overview": "Oversikt"') < source.index('"reports": "Rapporter"') < source.index('"orchestrator": "Orkestrering og tidsplan"')


def test_compact_report_actions_are_present():
    source = Path('market_intelligence.py').read_text(encoding='utf-8')
    for label in ['Kjør nytt utkast', 'Kjør morgenrapport', 'Kjør kveldsrapport', 'Åpne siste rapport']:
        assert label in source
    assert 'mi_catchup_{job.job_id}")' in source


def test_investor_edition_branding_and_version():
    version = Path('app_version.py').read_text(encoding='utf-8')
    report = Path('market_intelligence.py').read_text(encoding='utf-8')
    assert 'APP_VERSION = "v19.22.0-rc2"' in version
    assert 'Investor Edition' in report


def test_distribution_tools_follow_canonical_release():
    from app_version import APP_VERSION
    from tools.build_safe_distribution import VERSION as BUILD_VERSION
    from tools.validate_distribution import EXPECTED_VERSION
    assert BUILD_VERSION == APP_VERSION
    assert EXPECTED_VERSION == APP_VERSION
