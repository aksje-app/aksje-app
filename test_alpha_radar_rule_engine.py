from pathlib import Path

from alpha_radar_ui import _alpha_radar_rule_state, _default_signals_for_rules, _signal_options_for_rules


def test_alpha_radar_sources_follow_signal_lupe_without_old_defaults():
    state = _alpha_radar_rule_state(
        analysis_engine="Alpha Radar",
        mode="Blandet Alpha Radar",
        precision_level="Streng",
        market_cap_filter="Alle",
        selected_signals=["Nyheter/katalysator", "Insider/bjellesauer"],
        manual_sources={},
    )

    assert state["source_values"]["news"] is True
    assert state["source_locked"]["news"] is True
    assert state["source_values"]["insider"] is True
    assert state["source_locked"]["insider"] is True
    assert state["source_values"]["results"] is False
    assert state["source_locked"]["results"] is False


def test_optional_source_can_be_manual_without_becoming_required():
    state = _alpha_radar_rule_state(
        analysis_engine="Alpha Radar",
        mode="Blandet Alpha Radar",
        precision_level="Streng",
        market_cap_filter="Alle",
        selected_signals=["Nyheter/katalysator"],
        manual_sources={"results": True},
    )

    assert state["source_values"]["results"] is True
    assert state["source_locked"]["results"] is False
    assert state["source_status"]["results"] == "Valgfri pa"


def test_early_warning_overrides_require_news_and_insider():
    state = _alpha_radar_rule_state(
        analysis_engine="Early Warning V1",
        mode="Blandet Alpha Radar",
        precision_level="Streng",
        market_cap_filter="Alle",
        selected_signals=["Resultater"],
        manual_sources={},
    )

    assert state["effective_signals"] == ["Nyheter/katalysator", "Insider/bjellesauer", "Resultater"]
    assert state["source_locked"]["news"] is True
    assert state["source_locked"]["insider"] is True
    assert state["source_locked"]["results"] is True


def test_insider_mode_alpha_is_focused_not_news_default():
    defaults = _default_signals_for_rules("Alpha Radar", "Insider og bjellesauer", "Streng")
    state = _alpha_radar_rule_state(
        analysis_engine="Alpha Radar",
        mode="Insider og bjellesauer",
        precision_level="Streng",
        market_cap_filter="Alle",
        selected_signals=[],
        manual_sources={},
    )

    assert defaults == ["Insider/bjellesauer"]
    assert state["effective_signals"] == ["Insider/bjellesauer"]
    assert state["source_values"]["insider"] is True
    assert state["source_locked"]["insider"] is True
    assert state["source_values"]["news"] is False
    assert state["source_locked"]["news"] is False
    assert state["source_status"]["news"] == "Anbefalt"


def test_mode_filters_signal_options_and_reports_blocked_signals():
    state = _alpha_radar_rule_state(
        analysis_engine="Alpha Radar",
        mode="Insider og bjellesauer",
        precision_level="Streng",
        market_cap_filter="Alle",
        selected_signals=["Resultater", "Nyheter/katalysator"],
        manual_sources={},
    )

    assert "Resultater" not in _signal_options_for_rules("Alpha Radar", "Insider og bjellesauer")
    assert "Resultater" in state["blocked_signals"]
    assert state["effective_signals"] == ["Insider/bjellesauer", "Nyheter/katalysator"]
    assert state["source_values"]["results"] is False


def test_mode_required_signal_and_low_data_gate():
    defaults = _default_signals_for_rules("Alpha Radar", "Ravare/makro-medvind", "Streng")
    assert defaults[0] == "Ravarer/makro"

    strict = _alpha_radar_rule_state(
        analysis_engine="Alpha Radar",
        mode="Ravare/makro-medvind",
        precision_level="Streng",
        market_cap_filter="Alle",
        selected_signals=[],
    )
    exploratory = _alpha_radar_rule_state(
        analysis_engine="Alpha Radar",
        mode="Blandet Alpha Radar",
        precision_level="Utforskende",
        market_cap_filter="Alle",
        selected_signals=[],
    )

    assert strict["source_locked"]["macro"] is True
    assert strict["low_data_allowed"] is False
    assert exploratory["low_data_allowed"] is True


def test_no_heavy_calls_before_explicit_buttons_static_guard():
    ui = Path("alpha_radar_ui.py").read_text(encoding="utf-8", errors="ignore")
    button_pos = ui.find("run_clicked = st.button")
    assert button_pos > 0
    assert "run_alpha_radar(" not in ui[:button_pos]
    assert "run_early_warning(" not in ui[:button_pos]
    refresh_pos = ui.find("refresh_universe = st.button")
    resolve_pos = ui.find("resolve_tickers(scope")
    assert 0 < refresh_pos < resolve_pos < button_pos
    assert 'st.session_state[source_keys["news"]] = True' not in ui
    assert "_locked" in ui
    assert "alpha_radar_source_profile_" in ui
    app = Path("app.py").read_text(encoding="utf-8", errors="ignore")
    control_center_pos = app.find("render_ai_control_center(extra_panels=control_center_extra_panels_v18535())")
    finish_pos = app.find("_finish_control_center_render_cycle_v1863ax()", control_center_pos)
    stop_pos = app.find("st.stop()", control_center_pos)
    assert 0 < control_center_pos < finish_pos < stop_pos
