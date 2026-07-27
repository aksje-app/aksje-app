from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
APP = (ROOT / "app.py").read_text(encoding="utf-8")
VERSION = (ROOT / "app_version.py").read_text(encoding="utf-8")


def test_version_is_v1915():
    assert 'v19.0.15:' in VERSION and 'APP_VERSION = "v19.13.0"' in VERSION
    assert 'Mobil høyremeny og navigasjonshotfix' in VERSION


def test_responsive_sidebar_replaces_main_document_mobile_drawer():
    config = (ROOT / ".streamlit" / "config.toml").read_text(encoding="utf-8")
    assert "Do not inject a second mobile/navigation DOM into the main page" in APP
    assert '[data-testid="stSidebarNav"] { display:none !important; }' in APP
    assert "showSidebarNavigation = false" in config
    assert 'section[data-testid="stSidebar"]' in APP


def test_sidebar_navigation_contains_required_main_areas():
    sidebar = (ROOT / "ui_sidebar_stable.py").read_text(encoding="utf-8")
    required = ["Oversikt", "Autonomi", "Rapport", "Jobber", "Godkjenninger", "Portefølje", "Paper Trading", "Top Picks", "Analyse", "Varsler", "Valuta", "Innstillinger"]
    combined = APP + sidebar
    for label in required:
        assert label in combined


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
