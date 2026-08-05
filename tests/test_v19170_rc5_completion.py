from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]

def test_version_rc5():
    s=(ROOT/'app_version.py').read_text(encoding='utf-8')
    assert 'APP_VERSION = "v19.22.0-rc15"' in s

def test_paper_off_state_is_clean_and_links_to_drift_center():
    s=(ROOT/'pages/paper_trading.py').read_text(encoding='utf-8')
    assert 'Paper Trading er slått av i Driftssenter (steg 4)' in s
    assert 'paper_open_drift_center_v19170rc5' in s
    assert 'Detaljert blokkdiagnostikk skjules' in s

def test_banner_provider_aliases_and_intraday_display():
    app=(ROOT/'app.py').read_text(encoding='utf-8')
    ui=(ROOT/'ui/live_market_banner.py').read_text(encoding='utf-8')
    assert '"XAUUSD": "GC=F"' in app
    assert '"UKOILUSD": "BZ=F"' in app
    assert 'direction = "▲" if pct > 0 else ("▼" if pct < 0 else "•")' in ui
    assert 'f"{pct:+.2f}%"' in ui

def test_drift_center_has_next_step_help_and_hides_technical_names():
    s=(ROOT/'drift_center.py').read_text(encoding='utf-8')
    assert 'Neste anbefalte steg:' in s
    assert '_STEP_HELP' in s
    assert 'Tekniske Render-krav' in s
    assert 'Vanlige brukere trenger ikke forholde seg til variabelnavnene' in s

def test_navigation_fix_is_preserved():
    s=(ROOT/'ui_sidebar_stable.py').read_text(encoding='utf-8')
    assert 'every explicit sidebar click becomes the canonical active page' in s
    assert 'st.session_state["active_nav_target_v18674c"] = nav' in s

def test_production_is_fail_closed():
    s=(ROOT/'drift_center.py').read_text(encoding='utf-8')
    assert 'Steg {prior_step} må være effektivt aktivt først' in s
    assert 'requested["auto_trading_enabled"] = False' in s
