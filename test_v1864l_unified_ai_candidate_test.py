from pathlib import Path
import py_compile


ROOT = Path(__file__).resolve().parent


def test_v1864m_version_and_ai_candidate_cockpit_contract():
    for name in ["app.py", "workspace_layout.py", "app_version.py", "analysis.py", "analyst.py", "fmp_signals.py", "market_climate_engine.py", "market_climate_ui.py"]:
        py_compile.compile(str(ROOT / name), doraise=True)

    app = (ROOT / "app.py").read_text(encoding="utf-8", errors="ignore")
    layout = (ROOT / "workspace_layout.py").read_text(encoding="utf-8", errors="ignore")
    version = (ROOT / "app_version.py").read_text(encoding="utf-8", errors="ignore")

    assert 'APP_VERSION = "v18.6.13"' in version
    assert "Market Climate Explainability" in version
    assert "Markedsklima er lagt inn som egen modul" in version
    assert "Markedsklima er gjort om fra en abstrakt score til en forklarbar beslutningsstøtte med nivåer, terskler, tabeller og grafer" in version
    assert "lavt/normalt/høyt-nivåer" in version
    assert "Std klima-knapp" in version
    assert "Klimanivå, Klimaeffekt og Klimatolkning tidlig i resultatlisten" in version
    assert "Financial Modeling Prep som valgfri ny ekstern live-kilde" in version
    assert "bredere tickerunivers" in version
    assert "price target consensus" in version
    assert "ferske AI-signaler fra eksisterende Finnhub-moduler" in version
    assert "Analytiker-modulen leser nå miljø/secrets dynamisk" in version
    assert "Resultatsjokk krever nå faktisk surprise" in version
    assert "Utvalgsgrunnlag" in version
    assert "Prioritert bevis" in version
    assert "Resultatsjokk-søk skiller mellom bekreftet fundamentalt resultatsjokk" in version
    assert "printvennlige SVG-kurver" in version
    assert "label-tekst ikke overlapper" in version
    assert "kildestøtte-modus" in version
    assert "teknisk bevis" in version
    assert "Send Pushover-test" in version
    assert "Standard 1-6 mnd signalprofil" in version
    assert "AI Kandidattest kan velge flere kilder samtidig" in version
    assert "printvennlig HTML" in version

    assert "def render_ai_candidate_test_control_center_v1864l" in app
    assert '"AI Kandidattest", render_ai_candidate_test_control_center_v1864l' in app
    assert "from market_climate_ui import render_market_climate_panel" in app
    assert "from market_climate_engine import load_latest_market_climate_snapshot" in app
    assert '("Markedsklima", render_market_climate_panel)' in app
    assert "Finansavisen" in app and "Oljefond/NBIM" in app and "Folketrygdfondet" in app
    assert "force_manual_fetch=True" in app
    assert "include_insider=True" in app
    assert "AI_CANDIDATE_EVALUATION_DEFAULTS_V1864Q" in app
    assert "Kilder til AI Kandidattest" in app
    assert "Evalueringsoppsett" in app
    assert "Tidshorisont" in app
    assert "Standard" in app
    assert "Søkemodus / signalgrunnlag" in app
    assert "AI_CANDIDATE_SPECIAL_SEARCH_OPTIONS_V1864T" in app
    assert "AI_CANDIDATE_SOURCE_SUPPORT_MODES_V1864U" in app
    assert "source_support_mode" in app
    assert "AI_CANDIDATE_MARKET_CLIMATE_MODES_V1865" in app
    assert "market_climate_score_weight" in app
    assert "market_climate_cap_enabled" in app
    assert "market_climate_cap_threshold" in app
    assert "Std klima" in app
    assert "def _ai_candidate_market_climate_effect_v1865" in app
    assert "def _ai_candidate_runtime_config_with_climate_v1865" in app
    assert "def _ai_candidate_market_climate_level_v1866" in app
    assert "def _ai_candidate_market_climate_badge_v1866" in app
    assert "def _render_ai_candidate_climate_banner_v1866" in app
    assert "def _ai_candidate_market_climate_html_v1865" in app
    assert "Markedsklima ved kjøring" in app
    assert "Markedsklima" in app and "Klimamodus" in app and "Klimajustering" in app and "Klimabevis" in app
    assert "Klimanivå" in app and "Klimaeffekt" in app and "Klimatolkning" in app
    assert "Resultatsjokk" in app and "52-ukers breakout" in app
    assert "Volumbrudd" in app and "Katalysator-klynge" in app
    assert "Enkel ticker" in app
    assert "Detaljrapport" in app
    assert "Detalj Print/PDF HTML" in app
    assert "Utvalgsgrunnlag" in app
    assert "Bevisstatus" in app
    assert "Prioritert bevis" in app
    assert "Hvorfor ble aksjen valgt?" in app
    assert "Resultatsjokk ikke bekreftet" in app
    assert "EPS/omsetningssurprise mangler" in app
    assert "Ikke send / avvis" in app
    assert "def _ai_candidate_selection_evidence_v1864w" in app
    assert "def _ai_candidate_evidence_html_v1864w" in app
    assert "def _ai_candidate_enrich_live_signals_v1864x" in app
    assert "def _ai_candidate_fetch_live_signal_packet_v1864x" in app
    assert "def _ai_candidate_fmp_ready_v1864y" in app
    assert "fetch_fmp_signal_packet" in app
    assert "fmp_candidate_tickers" in app
    assert "FMP live" in app
    assert "FMP_API_KEY" in app
    assert "Ferske signalkilder" in app
    assert "Signalstatus" in app
    assert "Estimatgrunnlag" in app
    assert "Insidergrunnlag" in app
    assert "Resultatkalender" in app
    assert "live_signal_enrichment" in app
    assert "Ferske AI-signaler" in app
    assert "Momentumscore" in app and "Estimatløftscore" in app and "Eiertrykkscore" in app
    assert "Teknisk bevis" in app and "52u høy" in app and "Volum/20d" in app
    assert "def _render_ai_candidate_technical_chart_v1864u" in app
    assert "def _ai_candidate_detail_chart_blocks_html_v1864v" in app
    assert "def _ai_candidate_price_svg_v1864v" in app
    assert "def _ai_candidate_volume_svg_v1864v" in app
    assert "displayModeBar" in app and "False" in app
    assert "showlegend=False" in app
    assert "title_text=\"\"" in app
    assert "Legend holdes utenfor grafen" in app
    assert "report-chart" in app and "chart-block" in app
    assert "source_full_bonus_days" in app
    assert "relative_strength_weight" in app
    assert "estimate_revision_weight" in app
    assert "insider_buy_weight" in app
    assert "require_above_200dma" in app
    assert "warn_weak_liquidity" in app
    assert "Relativ styrke" in app
    assert "Estimatendringer" in app
    assert "Insiderkjop" in app
    assert "Sperrer/varsler" in app
    assert "Datamangler" in app
    assert "Hvordan evalueringen skjer" in app
    assert "Score" in app and "Confidence" in app and "Anbefaling" in app and "Varsel" in app
    assert "storage.write_json(\"analysis_snapshots/ai_candidate_test_latest.json\"" in app
    assert "storage.append_jsonl(\"analysis_snapshots/ai_candidate_test_runs.jsonl\"" in app
    assert "Print/PDF HTML" in app
    assert "JSON snapshot" in app
    assert "Datakildestatus / ferskhet" in app
    assert "evaluation_config" in app
    assert "Metode og evaluering" in app
    assert "source_status" in app
    assert "0 kandidater" in app
    assert "Land" in app and "Bors" in app and "Univers" in app
    assert "Kildestyrke" in app and "Endring" in app and "Forklaring" in app
    assert "Kildealder" in app and "historisk støtte" in app
    assert "def _load_ai_candidate_latest_result_v1864m" in app
    assert "Viser sist lagrede AI Kandidattest" in app
    assert "def _render_ai_candidate_selection_v1864m" in app
    assert "Top Picks" in app
    assert "Beslutning" in app
    assert "Paper" in app
    assert "Watchlist" in app
    assert "Sterk kandidat" in app and "Vurder" in app
    assert "set_cache_location" in (ROOT / "analysis.py").read_text(encoding="utf-8", errors="ignore")

    active_layout_block = layout[layout.index("def _render_ai_control_center_v1863aj") :]
    assert '"ai kandidattest", "kandidattest"' in active_layout_block
    assert "AI Kandidattest er hovedarbeidsflaten" in layout
    assert "AI Kandidattest: analyse, kilder og radarer" in layout
    assert "Kilder og import" in app
    assert "ai_candidate_source_hub_choice_v1864q" in app
    assert "ai_candidate_source_hub_quick_" not in app
    assert 'ai_candidate_group_name = "AI Kandidattest"' in active_layout_block
    assert "selected_group == ai_candidate_group_name and ai_candidate_primary_label in direct_panels" in active_layout_block
    assert '"folketrygdfondet"' in active_layout_block
    assert '"markedsklima"' in active_layout_block
    assert '"kilder"' in active_layout_block and '"import"' in active_layout_block
    assert "Ingen valgt" not in active_layout_block
    assert "Testflyt" not in layout
    assert "if len(direct_panels) == 1:" in layout
    assert "if len(direct_panels) > 1:" in layout
    assert "_render_pipeline_quick_start_v1863bx(panel_map, group_map)" not in active_layout_block


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








