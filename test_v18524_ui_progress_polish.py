from pathlib import Path


def test_ai_universe_mode_chips_are_live_not_form_buffered():
    src = Path("analysis_universe_ai.py").read_text(encoding="utf-8")
    assert "v18.5.26: no form wrapper here" in src
    assert "with st.form(\"ai_analysis_universe_form_v1853\"" not in src
    assert "Valgt nå:" in src
    assert "Sist lagret:" in src
    assert "ai_analysis_universe_save_v18524" in src


def test_progress_uses_rerun_pending_state_and_visible_progress_boxes():
    ai = Path("analysis_universe_ai.py").read_text(encoding="utf-8")
    basic = Path("strategy_testing_workspace.py").read_text(encoding="utf-8")
    pro = Path("strategy_test_pro.py").read_text(encoding="utf-8")
    assert "ai_universe_smart_run_pending_v18524" in ai
    assert "tl_basic_strategy_run_pending_v18524" in basic
    assert "run_pending_v18524" in pro
    assert "st.rerun()" in ai
    assert "st.rerun()" in basic
    assert "st.rerun()" in pro
    assert "rgba(56,189,248,.82)" in ai
    assert "border:2px solid rgba(56,189,248,.82)" in basic
    assert "border:2px solid rgba(56,189,248,.82)" in pro
    assert "ai_universe_visible_progress_v18526" in ai
    assert "ai-universe-visible-progress" in ai
    assert "time.sleep(0.55)" in ai
    assert "time.sleep(0.55)" in basic
    assert "time.sleep(0.55)" in pro


def test_banner_layout_has_extra_height_and_bottom_margin():
    app = Path("app.py").read_text(encoding="utf-8")
    assert "v18.5.26: stop banner text from being clipped" in app
    assert "min-height: 92px" in app
    assert "margin: 0.36rem 0 0.72rem 0" in app
    assert "aria-label='Ticker-banner'" in app
