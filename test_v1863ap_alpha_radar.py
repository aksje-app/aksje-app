from pathlib import Path
import py_compile


for name in [
    "alpha_radar_engine.py",
    "alpha_radar_ui.py",
    "alpha_radar_ownership.py",
    "alpha_radar_enrichment.py",
    "alpha_radar_currency.py",
    "alpha_radar_results.py",
    "actor_registry.py",
    "actor_registry_ui.py",
    "evidence_ledger.py",
    "financial_evidence_search.py",
    "nordic_actor_insider_search.py",
    "source_budget.py",
    "runtime_env.py",
    "data_source_diagnostics.py",
    "nordic_market_sources.py",
    "nbim_radar.py",
    "nbim_radar_ui.py",
    "decision_engine.py",
    "decision_ui.py",
    "early_warning_engine.py",
    "app.py",
    "workspace_layout.py",
    "app_version.py",
]:
    py_compile.compile(name, doraise=True)

engine = Path("alpha_radar_engine.py").read_text(encoding="utf-8", errors="ignore")
ui = Path("alpha_radar_ui.py").read_text(encoding="utf-8", errors="ignore")
results = Path("alpha_radar_results.py").read_text(encoding="utf-8", errors="ignore")
early = Path("early_warning_engine.py").read_text(encoding="utf-8", errors="ignore")
app = Path("app.py").read_text(encoding="utf-8", errors="ignore")
layout = Path("workspace_layout.py").read_text(encoding="utf-8", errors="ignore")
version = Path("app_version.py").read_text(encoding="utf-8", errors="ignore")
nbim_ui = Path("nbim_radar_ui.py").read_text(encoding="utf-8", errors="ignore")
nbim_engine = Path("nbim_radar.py").read_text(encoding="utf-8", errors="ignore")

assert 'APP_VERSION = "v18.6.3by"' in version
assert "Datagrunnlag Cockpit og Paper Position Actions" in version

# Alpha Radar must be a first-class Control Center panel.
assert "from alpha_radar_ui import render_alpha_radar_panel" in app
assert "from alpha_radar_enrichment import enrich_alpha_radar_row" in app
assert "from actor_registry_ui import render_actor_registry_panel" in app
assert "from nbim_radar_ui import render_nbim_radar_panel" in app
assert "def render_alpha_radar_control_center_v1863ap" in app
assert "data_enricher=enrich_alpha_radar_row" in app
assert "earnings_provider=get_earnings" in app
assert '("Alpha Radar", render_alpha_radar_control_center_v1863ap)' in app
assert '("Aktørregister", render_actor_registry_panel)' in app
assert '("Oljefond Radar", render_nbim_radar_panel)' in app
assert "from decision_ui import render_decision_support_panel" in app
assert '("Beslutningsgrunnlag", render_decision_support_panel)' in app
active_layout_block = layout.split("def _render_ai_control_center_v1863aj", 1)[1]
assert '"alpha"' in active_layout_block and '"muligheter"' in active_layout_block
assert '"beslut"' in active_layout_block and '"oljefond"' in active_layout_block and '"nbim"' in active_layout_block

# Heavy scanning must stay behind an explicit button.
button_pos = ui.find("run_clicked = st.button")
guard_pos = ui.find("if run_clicked and source_tickers:", button_pos)
if guard_pos < 0:
    guard_pos = ui.find("if run_clicked:", button_pos)
scan_pos = ui.find("run_alpha_radar(", button_pos)
assert 0 < button_pos < guard_pos < scan_pos
assert "run_alpha_radar(" not in ui[:button_pos]
refresh_pos = ui.find("refresh_universe = st.button")
resolve_pos = ui.find("resolve_tickers(scope")
assert 0 < refresh_pos < resolve_pos < button_pos
assert "Kjor Alpha Radar V2" in ui
assert "Contrarian / Hidden Potential Score" in ui
assert "ALPHA_RADAR_MODES" in ui
assert "MARKET_CAP_FILTERS" in ui
assert "PRECISION_LEVELS" in engine + ui
assert "normalize_alpha_radar_parameters" in engine + ui
assert "excluded_reason_counts" in engine + ui
assert "data_quality" in engine + ui
assert "warning_reasons" in engine + ui
assert "progress_callback" in engine + ui
assert "input_fingerprint" in ui + results
assert "max_selections=optional_limit" in ui
assert "Signal-lupe = vekting" in ui
assert "Datakilder = datagrunnlag" in ui
assert "_alpha_radar_rule_state" in ui
assert "_render_signal_rule_summary" in ui
assert "_render_market_audit" in ui
assert "Bruk modusprofil" in ui
assert "Kjoringsbudsjett / Run Preview" in ui
assert "0 tunge kall naa" in ui
assert "Kjor henter alltid ferskt run-univers" in ui
assert "balance_markets=balance_markets" in ui
assert "market_balance_enabled" in engine + ui + early
assert "market_cap_display" in engine + ui + results + early
assert "market_cap_currency" in engine + ui + results + early
assert "bjellesau_score" in engine + ui + results + early
assert "bjellesau_evidence" in engine + results + early
assert "split_ownership_evidence" in engine + early
assert "Send til Beslutningsgrunnlag" in ui
assert "DECISION_QUEUE_KEY" in ui
assert "Datakilde-status / markedstest" in ui
assert "Test datakilder per marked" in ui
assert "source_diagnostics" in engine + early + results
assert "Datadiagnostikk" in results
assert "search_financial_evidence" in Path("financial_evidence_search.py").read_text(encoding="utf-8", errors="ignore")
assert "financial_evidence_search" in Path("alpha_radar_enrichment.py").read_text(encoding="utf-8", errors="ignore")
assert "finans-/aktorsok opptil" in ui
assert "search_nordic_actor_insider" in Path("alpha_radar_enrichment.py").read_text(encoding="utf-8", errors="ignore")
assert "evidence_ledger" in engine + early + results
assert "source_budget_text" in ui
assert "Legg til aktør" in Path("actor_registry_ui.py").read_text(encoding="utf-8", errors="ignore")
assert "Unmatched Workbench" in Path("actor_registry_ui.py").read_text(encoding="utf-8", errors="ignore")
assert "Slett valgte" in Path("actor_registry_ui.py").read_text(encoding="utf-8", errors="ignore")
assert "Test aktør mot tekst" in Path("actor_registry_ui.py").read_text(encoding="utf-8", errors="ignore")
assert "local_market_source_diagnostics" in Path("nordic_market_sources.py").read_text(encoding="utf-8", errors="ignore")
assert "horizon_to_months" in ui + Path("data_source_diagnostics.py").read_text(encoding="utf-8", errors="ignore")
assert "data_window_months" in engine + early + ui + results
assert "build_decision_cases" in Path("decision_engine.py").read_text(encoding="utf-8", errors="ignore")
assert "render_decision_support_panel" in Path("decision_ui.py").read_text(encoding="utf-8", errors="ignore")
assert "Vurder hele køen" in Path("decision_ui.py").read_text(encoding="utf-8", errors="ignore")
assert "Tøm kø" in Path("decision_ui.py").read_text(encoding="utf-8", errors="ignore")
assert "universkilden har bare" in ui
assert "Enkeltmarked bruker egen grense" in ui
assert "alpha_news_quality" in engine
assert "Valgene er endret siden siste" in ui
assert "Venter på filer" in nbim_ui
assert "Matcher tickere / bygger overlay" in nbim_ui
assert "NBIM-watchlist" in nbim_ui
assert "Akkumulering svakhet" in nbim_ui
assert "Radar-overlap" in nbim_ui
assert "build_nbim_watchlist" in nbim_engine
assert "nbim_conviction_score" in nbim_engine
assert "market_value_nok_change_pct" in nbim_engine
assert "alpha_radar_result_to_csv" in ui + results
assert "alpha_radar_result_to_print_html" in ui + results
assert "Bruk som aktivt Analyseunivers" in ui
assert "Oppdater univers-preview" in ui
assert "run_early_warning" in ui + early
assert "Early Warning V1" in ui + early
assert "fresh_source_evidence" in early
assert "evidence_items" in early + results
assert "Euronext/Norden" in ui + results
assert "Standard/bred vekting" in ui
assert "alpha_radar_result_to_xlsx" in ui + results
assert "factor_quality" in engine + ui + results + early
assert "Presisjon" in ui
assert "Fyll opp lav-data" in ui
assert "crowding-straff" in ui
assert "fill_low_data" in engine
assert "crowdedness_penalty" in engine
assert "why_now" in engine
assert "reject_reasons" in engine
assert ".alpha-radar-row" in ui
assert "alpha-radar-grid" not in ui

# This is a hypothesis shortlist, not an execution surface.
for source in [engine, ui]:
    lowered = source.lower()
    assert "paper_buy" not in lowered
    assert "paper_sell" not in lowered
    assert "automatisk handel" in lowered or "ikke investeringsraad" in lowered or "hypotese" in lowered

# Do not reintroduce hidden legacy defaults in the new panel.
assert "AAPL" not in engine + ui
assert "MSFT" not in engine + ui
assert "NVDA" not in engine + ui
