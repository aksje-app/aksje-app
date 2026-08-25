from __future__ import annotations

import public_report_ui


def test_public_report_landing_preserves_program_tab_and_has_return_action():
    markup = public_report_ui._report_landing_actions(
        "/app/static/reports/public_report_SAFE_TOKEN.pdf"
    )

    assert 'target="_blank"' in markup
    assert 'rel="noopener noreferrer"' in markup
    assert 'href="/" target="_self"' in markup
    assert "Åpne PDF i ny fane" in markup
    assert "Tilbake til AI Aksje Analyzer" in markup
    assert "Tilbake til programmet" in markup
    assert '<iframe title="Rapportvisning"' in markup
    assert 'data-testid="public-report-mobile-shell"' in markup


def test_public_report_action_escapes_untrusted_url_content():
    markup = public_report_ui._report_landing_actions('/report.pdf" onmouseover="bad')

    assert 'onmouseover="bad' not in markup
    assert "&quot;" in markup


def test_public_report_module_has_no_top_level_navigation_replacement():
    source = open(public_report_ui.__file__, encoding="utf-8").read()

    assert "window.top.location.replace" not in source
    assert "window.top.location.assign" not in source
