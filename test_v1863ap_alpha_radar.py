from pathlib import Path
import py_compile


for name in [
    "alpha_radar_engine.py",
    "alpha_radar_ui.py",
    "app.py",
    "workspace_layout.py",
    "app_version.py",
]:
    py_compile.compile(name, doraise=True)

engine = Path("alpha_radar_engine.py").read_text(encoding="utf-8", errors="ignore")
ui = Path("alpha_radar_ui.py").read_text(encoding="utf-8", errors="ignore")
app = Path("app.py").read_text(encoding="utf-8", errors="ignore")
layout = Path("workspace_layout.py").read_text(encoding="utf-8", errors="ignore")
version = Path("app_version.py").read_text(encoding="utf-8", errors="ignore")

assert 'APP_VERSION = "v18.6.3aq"' in version
assert "Alpha Radar Hidden Potential V2" in version

# Alpha Radar must be a first-class Control Center panel.
assert "from alpha_radar_ui import render_alpha_radar_panel" in app
assert "def render_alpha_radar_control_center_v1863ap" in app
assert '("Alpha Radar", render_alpha_radar_control_center_v1863ap)' in app
active_layout_block = layout.split("def _render_ai_control_center_v1863aj", 1)[1]
assert '"alpha"' in active_layout_block and '"muligheter"' in active_layout_block

# Heavy scanning must stay behind an explicit button.
button_pos = ui.find("run_clicked = st.button")
guard_pos = ui.find("if run_clicked and source_tickers:", button_pos)
scan_pos = ui.find("run_alpha_radar(", button_pos)
assert 0 < button_pos < guard_pos < scan_pos
assert "run_alpha_radar(" not in ui[:button_pos]
assert "Kjor Alpha Radar V2" in ui
assert "Contrarian / Hidden Potential Score" in ui
assert "ALPHA_RADAR_MODES" in ui
assert "MARKET_CAP_FILTERS" in ui
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
