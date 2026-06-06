from pathlib import Path
import py_compile


ROOT = Path(__file__).resolve().parent


def test_v18610_banner_alerts_static_guards():
    for name in ["app.py", "app_version.py"]:
        py_compile.compile(str(ROOT / name), doraise=True)

    app = (ROOT / "app.py").read_text(encoding="utf-8", errors="ignore")
    version = (ROOT / "app_version.py").read_text(encoding="utf-8", errors="ignore")

    assert 'APP_VERSION = "v18.6.24"' in version
    assert "Sarskilt bannerklikk, fart og kompakte knapper" in version
    assert "BANNER_ALERT_CONFIG_KEY_V18610" in app
    assert "ALERT_LIFECYCLE_STATE_KEY_V18610" in app
    assert "_alert_lifecycle_update_v18610" in app
    assert "_apply_banner_alerts_v18610" in app
    assert "_render_banner_ticker_detail_v18610" in app
    assert "_render_banner_alert_settings_v18610" in app
    assert "_render_nordnet_datatest_v18610" in app
    assert "banner_ticker=" in app
    assert "live_banner_selected_ticker_v18610" in app
    assert "ticker-alert-marker" in app
    assert "Bannervarsler" in app
    assert "Nordnet datatest" in app
    assert "ALERT_LIFECYCLE_STATE_KEY_V18610" in app
    assert "transition.get(\"send\")" in app


def test_v18610_currency_uses_normal_reset_not_cooldown_only():
    app = (ROOT / "app.py").read_text(encoding="utf-8", errors="ignore")
    last_currency = app[app.rindex("def render_currency_alerts_control_center_v1863af") :]
    assert "_alert_lifecycle_update_v18610" in last_currency
    assert 'breach_status = "normal"' in last_currency
    assert 'breach_status = "breach_lower"' in last_currency
    assert 'breach_status = "breach_upper"' in last_currency
    assert 'if transition.get("send"):' in last_currency
    assert "transition = _alert_lifecycle_update_v18610" in last_currency






