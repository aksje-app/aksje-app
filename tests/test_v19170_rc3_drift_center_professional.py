from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_professional_status_and_progress_are_present():
    text = (ROOT / "drift_center.py").read_text(encoding="utf-8")
    assert "Fremdrift:" in text
    assert "Status trinn 1–8" in text
    assert '"PÅ": ("🟢", "Aktiv")' in text
    assert '"AV": ("🔴", "Av")' in text
    assert '"VENTER": ("🟡", "Venter")' in text


def test_activation_flow_has_visible_status_log():
    text = (ROOT / "drift_center.py").read_text(encoding="utf-8")
    assert "with st.status(" in text
    assert "Kontrollerer tidligere trinn" in text
    assert "Lagrer ønsket status" in text


def test_production_trade_is_separate_and_fail_closed():
    text = (ROOT / "drift_center.py").read_text(encoding="utf-8")
    assert "Produksjonshandel · steg 8" in text
    assert "prior_ready = all(" in text
    assert "Aktiver produksjonshandel" in text
    assert "Deaktiver produksjonshandel" in text


def test_release_version_is_release_candidate():
    text = (ROOT / "app_version.py").read_text(encoding="utf-8")
    assert 'APP_VERSION = "v19.22.0-rc' in text
