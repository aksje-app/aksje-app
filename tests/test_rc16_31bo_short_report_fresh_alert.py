from pathlib import Path

from app_version import APP_VERSION, PREVIOUS_APP_VERSION


def test_bo_version_contract():
    assert APP_VERSION == "v19.22.0-rc16.31bo"
    assert PREVIOUS_APP_VERSION == "v19.22.0-rc16.31bn"


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
    assert 'fresh_watch_short = [row for row in fresh_watch_short if isinstance(row, Mapping)][:3]' in src
    assert 'Full forklaring med RSI, OBV, breakout' in src
    assert '"relativ styrke, støtte/motstand og ekstra nyhets-/insider-/shortkontroll ligger i teknisk vedlegg."' in src
    assert '"Dette er observasjonssignaler, ikke kjøpsfullmakt.' in src
