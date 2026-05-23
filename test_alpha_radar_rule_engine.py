from pathlib import Path

from alpha_radar_ui import _alpha_radar_rule_state, _default_signals_for_rules


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
