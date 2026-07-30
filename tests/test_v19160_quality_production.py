from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_streamlit_deprecations_removed_from_runtime_python():
    offenders = []
    for path in ROOT.rglob("*.py"):
        if "tests" in path.parts:
            continue
        text = path.read_text(encoding="utf-8")
        if "use_container_width=" in text or "components.html(" in text or "st.components.v1.html(" in text:
            offenders.append(str(path.relative_to(ROOT)))
    assert offenders == []


def test_control_center_radio_does_not_mix_state_and_default():
    text = (ROOT / "workspace_layout.py").read_text(encoding="utf-8")
    assert 'group_radio_kwargs = {' in text
    assert 'if group_radio_key not in st.session_state' in text
    assert '**group_radio_kwargs' in text


def test_pdf_has_explicit_draft_banner_and_confidence_explanation():
    text = (ROOT / "market_intelligence.py").read_text(encoding="utf-8")
    assert "UTKAST – AVVENTER ENDELIG VALIDERING" in text
    assert "confidence_bar" in text
    assert "Konfidensforklaring" in text
    assert "Ikke søkt" in text
    assert "Kildefeil" in text
    assert "Foreldede data" in text
