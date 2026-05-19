from pathlib import Path

from market_universe import MARKET_SCOPE_OPTIONS, picker_scope_options


def test_shared_market_options_cover_requested_markets():
    for market in ["USA", "Norge", "Sverige", "Finland", "Danmark", "Brasil", "Norden", "Alle"]:
        assert market in MARKET_SCOPE_OPTIONS
        assert market in picker_scope_options(include_sources=True)


def test_ai_universe_uses_shared_market_options_and_empty_default():
    text = Path("analysis_universe_ai.py").read_text(encoding="utf-8", errors="ignore")
    assert "MARKET_SCOPES = picker_scope_options(include_sources=True)" in text
    assert '"scopes": st.session_state.get("ai_universe_scopes_draft_v1853", [])' in text
    assert 'or ["USA"]' not in text[text.find("scopes = st.multiselect"):text.find("manual_ticker = st.text_input")]


def test_testing_learning_is_manual_ticker_input_not_seed_dropdown():
    text = Path("strategy_testing_workspace.py").read_text(encoding="utf-8", errors="ignore")
    assert 'st.text_input(' in text
    assert 'st.selectbox("Ticker for testing"' not in text
    assert 'def render_strategy_testing_workspace(ticker: str = "")' in text
