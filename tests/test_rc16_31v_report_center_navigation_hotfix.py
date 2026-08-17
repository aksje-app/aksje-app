from pathlib import Path

from app_version import APP_VERSION, PREVIOUS_APP_VERSION


ROOT = Path(__file__).resolve().parents[1]


def test_release_identity_is_directly_based_on_rc16_31u():
    assert APP_VERSION == "v19.22.0-rc16.31v"
    assert PREVIOUS_APP_VERSION == "v19.22.0-rc16.31u"


def test_report_center_does_not_call_private_app_persistence_function():
    source = (ROOT / "market_intelligence.py").read_text(encoding="utf-8")
    report_center = source[source.index("def render_market_intelligence()") :]
    assert "_persist_ui_state_v18658(" not in report_center
    assert "set_global_navigation_state(" in report_center
    for label in (
        "Rapporter, historikk og avansert",
        "Kjøring og fremdrift",
        "Hurtigarkiv og komplett ZIP",
    ):
        assert label in report_center


def test_autonomy_page_does_not_call_private_app_persistence_function():
    source = (ROOT / "pages" / "autonomy.py").read_text(encoding="utf-8")
    assert "_persist_ui_state_v18658(" not in source
    assert "set_global_navigation_state(" in source
