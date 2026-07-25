from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
APP = (ROOT / "app.py").read_text(encoding="utf-8")
VERSION = (ROOT / "app_version.py").read_text(encoding="utf-8")


def test_version_is_v1915():
    assert 'v19.0.15:' in VERSION and 'APP_VERSION = "v19.0.19a"' in VERSION
    assert 'Mobil høyremeny og navigasjonshotfix' in VERSION


def test_mobile_drawer_exists_and_is_not_sidebar_dependent():
    assert 'mobile-drawer-v19015' in APP
    assert 'mobile-drawer-panel-v19015' in APP
    assert 'role="navigation" aria-label="Mobil hovedmeny"' in APP
    assert 'Åpne mobilmeny' in APP
    # Sidebar may still be hidden on mobile, but the drawer is rendered in main DOM.
    assert 'section[data-testid="stSidebar"]' in APP
    assert '_mobile_drawer_items_v19015' in APP


def test_mobile_drawer_contains_required_main_areas():
    required = [
        'Oversikt',
        'Autonomi',
        'Rapporter',
        'Jobber / Planlegger',
        'Ventende godkjenninger',
        'Læringsportefølje',
        'Paper Trading',
        'Top Picks',
        'Analyse',
        'Varsler',
        'Valuta',
        'Systemstatus',
    ]
    for label in required:
        assert label in APP


def test_mobile_routes_cover_jobs_approvals_alerts_and_system():
    for route in ['"jobs": _mobile_nav_href_v18646("jobs")', '"approvals": _mobile_nav_href_v18646("approvals")', '"alerts": _mobile_nav_href_v18646("alerts")', '"system": _mobile_nav_href_v18646("system")']:
        assert route in APP
    assert 'if nav in {"jobber", "jobs", "scheduler", "planlegger", "tidsplan"}' in APP
    assert 'nav = "approvals"' in APP
    assert 'nav = "operations"' in APP
    assert 'nav = "system"' in APP


def test_admin_and_drift_no_long_mobile_wrapping_labels():
    assert 'st.columns([1.8, 1.8, 5.4])' in APP
    assert 'st.button("Admin", key="top_admin_menu_v18647"' in APP
    assert 'st.button("Drift" if not _drift_now_v18647 else "Skjul", key="top_drift_menu_v18647"' in APP
