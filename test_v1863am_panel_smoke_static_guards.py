from pathlib import Path
import py_compile


for name in ["app.py", "workspace_layout.py", "daily_ai_market_report.py", "forecast_ui.py", "analysis_universe_ai.py"]:
    py_compile.compile(name, doraise=True)

app = Path("app.py").read_text(encoding="utf-8", errors="ignore")
layout = Path("workspace_layout.py").read_text(encoding="utf-8", errors="ignore")
daily = Path("daily_ai_market_report.py").read_text(encoding="utf-8", errors="ignore")
forecast = Path("forecast_ui.py").read_text(encoding="utf-8", errors="ignore")
analysis = Path("analysis_universe_ai.py").read_text(encoding="utf-8", errors="ignore")

# Panels should render as explicit tasks and not run hidden heavy work on open.
assert "Rapporten kj" in daily and "ikke automatisk" in daily
assert "Ingen oppgave er åpnet" in layout or "Ingen oppgave er Ã¥pnet" in layout
assert "Oppdater AI Market Briefing" in daily
assert "Lag portef" in forecast
assert "Kjor Smart AI-utvalg" in analysis or "KjÃ¸r Smart AI-utvalg" in analysis

assert "tickerliste/univers" in analysis
assert "scorede kandidater" in analysis
assert "Preview av eksisterende scorede/cache-kandidater" in analysis

# Known heavy calls should remain behind explicit buttons in the most sensitive panels.
daily_run_pos = daily.find("run = st.button")
daily_build_pos = daily.find("build_daily_market_report")
assert daily_run_pos > 0 and daily_build_pos > 0
assert "if run:" in daily[daily_run_pos:daily_run_pos + 500]

top_picks_pos = app.find("def render_top_picks_control_center_v1863s")
assert top_picks_pos > 0
top_picks_block = app[top_picks_pos: app.find("def render_watchlist_signals_control_center_v18535", top_picks_pos)]
assert "if run_clicked" in top_picks_block
assert "cached_auto_rank_market" in top_picks_block

# Basic static visual guard against accidentally adding large white placeholder panes.
for source in [daily, forecast, analysis, layout]:
    lowered = source.lower()
    assert "background:white" not in lowered
    assert "background: #fff" not in lowered
    assert "background-color:white" not in lowered
    assert "height:100vh" not in lowered

