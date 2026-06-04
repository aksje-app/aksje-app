from pathlib import Path
import py_compile


ROOT = Path(__file__).resolve().parent


def _read(name: str) -> str:
    return (ROOT / name).read_text(encoding="utf-8", errors="ignore")


def test_banner_down_thresholds_are_streamlit_safe():
    app = _read("app.py")
    py_compile.compile(str(ROOT / "app.py"), doraise=True)

    assert "def _normalize_down_pct_input_v18616" in app
    assert "merged[\"common_pct_down\"] = _normalize_down_pct_input_v18616" in app
    assert "value=_normalize_down_pct_input_v18616(config.get(\"common_pct_down\", 0.0))" in app
    assert "value=_normalize_down_pct_input_v18616(current.get(\"pct_down\", 0.0))" in app


def test_banner_forms_have_submit_buttons_and_visible_follow_controls():
    app = _read("app.py")

    assert 'submitted = st.form_submit_button("Lagre og bruk banner", use_container_width=True)' in app
    assert 'submitted = _global_apply_requested_v161()' not in app
    assert "Missing Submit Button" not in app
    assert "Særskilt overvåking" in app
    assert '"Hastighet sekunder"' in app


def test_full_pytest_collects_new_v1861_tests():
    pytest_ini = _read("pytest.ini")
    version = _read("app_version.py")

    assert "test_v1861*.py" in pytest_ini
    assert 'APP_VERSION = "v18.6.22"' in version
    assert "Refresh-login uten fastlaast restore" in version



