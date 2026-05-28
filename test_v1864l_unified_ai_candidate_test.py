from pathlib import Path
import py_compile


ROOT = Path(__file__).resolve().parent


def test_v1864m_version_and_ai_candidate_cockpit_contract():
    for name in ["app.py", "workspace_layout.py", "app_version.py", "analysis.py"]:
        py_compile.compile(str(ROOT / name), doraise=True)

    app = (ROOT / "app.py").read_text(encoding="utf-8", errors="ignore")
    layout = (ROOT / "workspace_layout.py").read_text(encoding="utf-8", errors="ignore")
    version = (ROOT / "app_version.py").read_text(encoding="utf-8", errors="ignore")

    assert 'APP_VERSION = "v18.6.4n"' in version
    assert "AI Candidate Hub" in version
    assert "AI Kandidattest samler fersk kandidatfangst" in version
    assert "printvennlig HTML" in version

    assert "def render_ai_candidate_test_control_center_v1864l" in app
    assert '"AI Kandidattest", render_ai_candidate_test_control_center_v1864l' in app
    assert "Finansavisen" in app and "Oljefond/NBIM" in app and "Folketrygdfondet" in app
    assert "force_manual_fetch=True" in app
    assert "include_insider=True" in app
    assert "Score" in app and "Confidence" in app and "Anbefaling" in app and "Varsel" in app
    assert "storage.write_json(\"analysis_snapshots/ai_candidate_test_latest.json\"" in app
    assert "storage.append_jsonl(\"analysis_snapshots/ai_candidate_test_runs.jsonl\"" in app
    assert "Print/PDF HTML" in app
    assert "JSON snapshot" in app
    assert "Datakildestatus / ferskhet" in app
    assert "source_status" in app
    assert "Kjoringen er lagret, men ga 0 kandidater" in app
    assert "Land" in app and "Bors" in app and "Univers" in app
    assert "Kildestyrke" in app and "Endring" in app and "Forklaring" in app
    assert "def _load_ai_candidate_latest_result_v1864m" in app
    assert "Viser sist lagrede AI Kandidattest" in app
    assert "def _render_ai_candidate_selection_v1864m" in app
    assert "Send valgte til Top Picks" in app
    assert "Send til Beslutningsgrunnlag" in app
    assert "Send til Paper Trading" in app
    assert "Legg i Watchlist" in app
    assert "Sterk kandidat" in app and "Vurder" in app
    assert "set_cache_location" in (ROOT / "analysis.py").read_text(encoding="utf-8", errors="ignore")

    active_layout_block = layout[layout.index("def _render_ai_control_center_v1863aj") :]
    assert '"ai kandidattest", "kandidattest"' in active_layout_block
    assert "AI Kandidattest er hovedarbeidsflaten" in layout
    assert "AI Kandidattest: analyse, kilder og radarer" in layout
    assert 'ai_candidate_group_name = "AI Kandidattest"' in active_layout_block
    assert "selected_group == ai_candidate_group_name and ai_candidate_primary_label in direct_panels" in active_layout_block
    assert '"folketrygdfondet"' in active_layout_block
    assert '_matching_panel_labels("finansavisen", "bjellesauer", "folketrygdfondet")' in active_layout_block
    assert "Testflyt" not in layout
    assert "if len(direct_panels) == 1:" in layout
    assert "if len(direct_panels) > 1:" in layout
    assert 'pending_nav_sync["group"] = stage_group_name' in active_layout_block


def test_v1864m_start_empty_sidebar_view_removed_and_ticker_input_kept():
    app = (ROOT / "app.py").read_text(encoding="utf-8", errors="ignore")

    view_block = app[app.index('st.session_state["global_view_mode_v145"] = "Full"') - 250 : app.index('st.session_state["global_view_mode_v145"] = "Full"') + 250]
    assert 'st.radio("Visning"' not in view_block
    assert 'APP_VIEW_MODE = "Full"' in view_block

    startup_block = app[app.index("ai_control_center_landed_default_v1864l") - 250 : app.index("ai_control_center_landed_default_v1864l") + 420]
    assert 'st.session_state.setdefault("ai_control_center_group_v1863aj", "")' in startup_block
    assert 'st.session_state.setdefault("ai_control_center_active_panel_v1863aj", "")' in startup_block
    assert "Marked og signaler" not in startup_block
    assert '"Marked"' not in startup_block

    cleanup_block = app[app.index("def _cleanup_legacy_session_seed_data_v1863t") : app.index("def active_ticker_from_inputs")]
    assert "cc_interactive_ticker_v18535" not in cleanup_block
    assert 'key="cc_interactive_ticker_v18535"' in app
