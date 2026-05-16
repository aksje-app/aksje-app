from pathlib import Path

APP = Path('app.py').read_text(encoding='utf-8')


def test_v18597_final_css_is_late_and_targets_real_streamlit_buttons():
    assert 'v18.5.97: Final desktop truth patch after all legacy CSS' in APP
    assert 'div[data-testid="stButton"] > button' in APP
    assert 'div[data-testid="stFormSubmitButton"] > button' in APP
    assert 'width:100% !important;' in APP
    assert 'overflow:visible !important;' in APP


def test_v18597_hides_streamlit_runtime_stop_overlay():
    assert '[data-testid="stStatusWidget"]' in APP
    assert '[data-testid="stToolbar"]' in APP
    assert 'display:none !important;' in APP


def test_v18597_pushover_buttons_remain_visible_without_env():
    assert 'main_auto_verify_pushover_v18595_desktop_visible' in APP
    assert 'main_auto_send_test_pushover_v18595_desktop_visible' in APP
    assert 'disabled=False' in APP
    assert 'Pushover-token eller user-key mangler' in APP


def test_v18597_topbar_no_artificial_chat_padding():
    assert 'padding-right:.82rem !important;' in APP
    assert '.v18534-control-button-gap' in APP
