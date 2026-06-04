from pathlib import Path
import py_compile


ROOT = Path(__file__).resolve().parent


def _read(name: str) -> str:
    return (ROOT / name).read_text(encoding="utf-8", errors="ignore")


def test_v18621_version_and_auth_restore_refresh_guard():
    version = _read("app_version.py")
    auth = _read("auth.py")
    py_compile.compile(str(ROOT / "auth.py"), doraise=True)

    assert 'APP_VERSION = "v18.6.21"' in version
    assert "Refresh-login, saerskilt bannerlogikk og manuell NAV" in version
    assert "auth_restore_attempted_v18621" in auth
    assert "Gjenoppretter innlogging på denne enheten" in auth
    assert 'parentUrl.searchParams.set("remember_token", token)' in auth


def test_v18621_special_watch_has_own_speed_alerts_and_log_controls():
    app = _read("app.py")
    py_compile.compile(str(ROOT / "app.py"), doraise=True)

    assert "SPECIAL_WATCH_ALERT_LOG_KEY_V18621" in app
    assert "specialWatchTickerTapeScrollV18621" in app
    assert "special-watch-track-v18621" in app
    assert 'source="special_watch_banner"' in app
    assert 'log_key=SPECIAL_WATCH_ALERT_LOG_KEY_V18621' in app
    assert "Gul nær grense %" in app
    assert "Send Pushover ved rød markør" in app
    assert "Signalhistorikk for særskilt overvåking" in app
    assert "Tøm særskilt logg" in app
    assert "Tøm bannervarsler" in app


def test_v18621_paper_nav_and_existing_hypothesis_text():
    app = _read("app.py")

    assert "def _render_manual_paper_nav_update_v18621" in app
    assert "Manuell kurs/NAV for paper-beholdning" in app
    assert "Lagre manuell kurs/NAV" in app
    assert "Bruk Manuell kurs/NAV under" in app
    assert "def _paper_hypothesis_matches_position_v18621" in app
    assert "Finnes i beholdning" in app
    assert "Følg opp / øk / oppdater vurdering" in app
