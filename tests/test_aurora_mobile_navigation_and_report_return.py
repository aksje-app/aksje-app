from __future__ import annotations

from pathlib import Path

import public_report_ui
from ui_library import shell, theme


class _MarkdownRecorder:
    def __init__(self):
        self.blocks: list[str] = []

    def markdown(self, value: str, **_kwargs) -> None:
        self.blocks.append(value)


def test_mobile_shell_has_one_primary_rail_and_complete_more_menu():
    st = _MarkdownRecorder()

    shell.render_shell(st, "overview", {})

    markup = "\n".join(st.blocks)
    assert markup.count('class="aa-mobile-nav"') == 1
    assert 'class="aa-mobile-more"' in markup
    for label in (
        "Autonomi",
        "Rapporter",
        "Jobber/planlegger",
        "Godkjenninger",
        "Paper Trading",
        "Valuta",
        "Drift",
        "Innstillinger",
    ):
        assert label in markup


def test_aurora_mobile_css_hides_legacy_sidebar_and_keeps_nav_clickable():
    st = _MarkdownRecorder()

    theme.inject_design_system(st, module="overview")

    css = "\n".join(st.blocks)
    assert 'section[data-testid="stSidebar"]' in css
    assert 'data-testid="stSidebarCollapsedControl"' in css
    assert "pointer-events:none" in css
    assert ".aa-mobile-nav" in css
    assert "pointer-events:auto" in css
    assert "-webkit-text-fill-color" in css


def test_aurora_css_is_injected_after_legacy_sidebar_css():
    source = Path("app.py").read_text(encoding="utf-8")

    assert source.index("render_stable_sidebar_v18641(") < source.index("inject_design_system(st, module=_ab_route)")


def test_public_report_return_target_is_allowlisted_and_preserved():
    assert public_report_ui._report_return_href("portfolio") == "/?aa_nav=portfolio"
    assert public_report_ui._report_return_href("reports") == "/?aa_nav=reports"
    assert public_report_ui._report_return_href("https://evil.invalid/") == "/?aa_nav=reports"

    markup = public_report_ui._report_landing_actions(
        "/app/static/reports/public_report_SAFE_TOKEN.pdf",
        return_href="/?aa_nav=portfolio",
    )
    assert markup.count('href="/?aa_nav=portfolio" target="_self"') == 1


def test_internal_report_url_can_carry_safe_return_route():
    url = public_report_ui.with_report_return(
        "https://aksje-app.onrender.com/?public_report_token=" + "A" * 43,
        "portfolio",
    )
    assert "public_report_token=" + "A" * 43 in url
    assert "return_to=portfolio" in url
    assert public_report_ui.with_report_return("javascript:bad", "portfolio") == ""
