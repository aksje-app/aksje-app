from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
APP = (ROOT / 'app.py').read_text(encoding='utf-8')
UI = (ROOT / 'ui' / 'live_market_banner.py').read_text(encoding='utf-8')
VERSION = (ROOT / 'app_version.py').read_text(encoding='utf-8')


def test_rc7_version():
    assert 'APP_VERSION = "v19.22.0-rc10"' in VERSION


def test_macro_aliases_are_provider_specific():
    assert '"XAUUSD": "GC=F"' in APP
    assert '"UKOILUSD": "BZ=F"' in APP
    assert '"XAUUSD=F": "XAUUSD"' in APP
    assert '"UKOILUSD=F": "UKOILUSD"' in APP
    assert '"XAUUSD": "Gull"' in APP
    assert '"UKOILUSD": "Brent Spot"' in APP


def test_banner_deduplicates_after_canonicalization():
    assert 'seen = set()' in APP
    assert 'if not key or key in seen:' in APP
    assert 'seen.add(key)' in APP


def test_missing_data_does_not_show_fake_zero_change():
    assert "Ingen markedsdata" in UI
    assert 'if price_missing' in UI
    assert 'change_html = (' in UI


def test_banner_has_room_for_change_line():
    assert 'height: 66px;' in UI
    assert 'min-height: 80px;' in UI
    assert '.ticker-change.pos' in UI
    assert '.ticker-change.neg' in UI
    assert '.ticker-change.missing' in UI


def test_detail_lookup_uses_provider_alias():
    assert 'ticker = _live_banner_provider_ticker_v19170rc5' in APP
