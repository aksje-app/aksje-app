from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
APP = (ROOT / 'app.py').read_text(encoding='utf-8')
UI = (ROOT / 'ui' / 'live_market_banner.py').read_text(encoding='utf-8')
VERSION = (ROOT / 'app_version.py').read_text(encoding='utf-8')


def test_rc6_version():
    assert 'APP_VERSION = "v19.22.0-rc14"' in VERSION


def test_provider_aliases_and_wrong_suffixes_are_normalised():
    assert '"XAUUSD": "GC=F"' in APP
    assert '"UKOILUSD": "BZ=F"' in APP
    assert '"XAUUSD=F": "XAUUSD"' in APP
    assert '"UKOILUSD=F": "UKOILUSD"' in APP


def test_fallback_uses_provider_ticker():
    assert '_close_from_banner_history(history, provider_ticker)' in APP


def test_main_banner_has_direction_arrows():
    assert 'direction = "▲" if pct > 0 else ("▼" if pct < 0 else "•")' in UI
    assert "{direction} {pct_txt}" in UI


def test_special_banner_has_direction_arrows():
    assert "{'▲' if pct > 0 else ('▼' if pct < 0 else '•')} {pct:+.2f}%" in APP


def test_final_css_does_not_clip_change_line():
    assert 'height: 58px !important;' in APP
    assert 'max-height: none !important;' in APP
    assert '.ticker-change {' in APP
    assert 'overflow: visible !important;' in APP
