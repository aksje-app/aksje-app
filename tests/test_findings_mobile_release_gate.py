"""Release regression checks for the mobile findings shortcut and panels."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_findings_modules_compile():
    for path in (
        "strategy_history_progress_view.py",
        "research_findings_dashboard.py",
        "ui_library/shell.py",
        "pages/autonomy.py",
    ):
        source = (ROOT / path).read_text(encoding="utf-8")
        compile(source, path, "exec")


def test_mobile_findings_shortcut_and_market_fallback():
    from ui_library.shell import MOBILE_ROUTES, MORE_ROUTES, _LEGACY_TARGETS
    assert any(route.slug == "findings" and route.label == "Funn" for route in MOBILE_ROUTES)
    assert not any(route.slug == "market" for route in MOBILE_ROUTES)
    assert any(route.slug == "market" for route in MORE_ROUTES)
    assert _LEGACY_TARGETS["findings"] == "autonomy"


def test_findings_panel_is_reachable_from_autonomy():
    source = (ROOT / "pages/autonomy.py").read_text(encoding="utf-8")
    assert "show_interim_research_findings" in source
    assert "research_findings_dashboard" in source
