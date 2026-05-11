from pathlib import Path


def test_ai_universe_uses_toggle_not_expander_for_roadmap_and_guards_white_panels():
    src = Path("analysis_universe_ai.py").read_text(encoding="utf-8")
    assert "ai_universe_show_roadmap_v18526" in src
    assert 'with st.expander("Vis roadmap / detaljstatus for funksjonene"' not in src
    assert "v18.5.26 final null-panel guard" in src
    assert 'div[data-testid="stDataFrame"]' in src
    assert 'div[data-testid="stExpander"]' in src


def test_visible_progress_snapshot_is_persistent_for_smart_ai():
    src = Path("analysis_universe_ai.py").read_text(encoding="utf-8")
    assert "AI_UNIVERSE_VISIBLE_PROGRESS_KEY" in src
    assert "def _render_progress_snapshot" in src
    assert "_render_progress_snapshot()" in src
    assert "🔄 Kjører {title}" in src
