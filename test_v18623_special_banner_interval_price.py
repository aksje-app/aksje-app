from pathlib import Path

ROOT = Path(__file__).resolve().parent


def test_v18623_version_label():
    namespace = {}
    exec((ROOT / "app_version.py").read_text(encoding="utf-8"), namespace)
    assert namespace["APP_VERSION"] == "v18.6.23"
    assert namespace["APP_VERSION_NAME"] == "Sarskilt bannerintervall og tydelig kursvisning"
    assert namespace["APP_BUILD_ID"] == "v18623-special-banner-interval-price"


def test_v18623_special_watch_has_own_interval_and_speed_language():
    source = (ROOT / "app.py").read_text(encoding="utf-8")
    assert "special_watch_update_interval_minutes_v18623" in source
    assert "special_watch_refresh_v18623" in source
    assert "0 = bruk hovedbannerets oppdateringsintervall" in source
    assert "Lavere tall ruller raskere" in source
    assert "Høyere tall ruller saktere" in source


def test_v18623_special_watch_normalizes_short_tape_width():
    source = (ROOT / "app.py").read_text(encoding="utf-8")
    assert "render_cards_html_v18623" in source
    assert "len(render_cards_html_v18623) < 12" in source
    assert "specialWatchTickerTapeScrollV18621" in source
    assert "data ca. hver {refresh_minutes}. min" in source


def test_v18623_detail_ticker_header_and_price_missing_guard():
    source = (ROOT / "app.py").read_text(encoding="utf-8")
    assert "banner-detail-ticker-card-v18623" in source
    assert "status-green" in source
    assert "status-yellow" in source
    assert "status-red" in source
    assert "def _banner_price_text_v18623" in source
    assert 'return "-"' in source


def test_v18623_fallback_uses_close_not_fake_zero():
    source = (ROOT / "app.py").read_text(encoding="utf-8")
    fallback_start = source.index("def _banner_fallback_cards_v18614")
    fallback_end = source.index("def _banner_price_text_v18623")
    fallback = source[fallback_start:fallback_end]
    assert "_download_live_banner_history" in fallback
    assert "_close_from_banner_history" in fallback
    assert '"price": price' in fallback
    assert '"price_missing": price is None' in fallback
    assert '"price_source": price_source' in fallback
    assert "Sluttkurs" in fallback
