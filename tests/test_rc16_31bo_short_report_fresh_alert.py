from pathlib import Path

from app_version import APP_VERSION, PREVIOUS_APP_VERSION


def test_bo_version_contract():
    from release_contract_checks import assert_current_release
    assert_current_release()


def test_short_report_surfaces_fresh_trend_before_technical_gate():
    src = Path("market_intelligence.py").read_text(encoding="utf-8")
    short_heading = 'Paragraph("⚡ Nye tidlige styrkesignaler"'
    technical_heading = 'Paragraph("Fresh Trend – nye aksjer som akkurat akselererer"'
    technical_gate = "if has_technical_content and include_technical:"
    assert short_heading in src
    assert technical_heading in src
    assert technical_gate in src
    assert src.index(short_heading) < src.index(technical_gate)
    assert src.index(technical_heading) < src.index(technical_gate)


def test_short_report_is_limited_and_points_to_technical_details():
    src = Path("market_intelligence.py").read_text(encoding="utf-8")
    assert 'for receipt in fresh_watch_short[:3]:' in src
    assert '_trend_chart({"trend_receipt": receipt}' in src
    assert 'fresh_signal' in src and 'momentum 3d' in src
    assert 'observasjon' in src and 'ikke kjøpsfullmakt' in src
