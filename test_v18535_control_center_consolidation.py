from pathlib import Path
import py_compile

for name in ["app.py", "workspace_layout.py", "app_version.py"]:
    py_compile.compile(name, doraise=True)

app = Path("app.py").read_text(encoding="utf-8", errors="ignore")
layout = Path("workspace_layout.py").read_text(encoding="utf-8", errors="ignore")
version = Path("app_version.py").read_text(encoding="utf-8", errors="ignore")

assert 'APP_VERSION = "v18.6.3bi"' in version
assert "def render_ai_control_center(extra_panels" in layout
assert "st.tabs(" not in layout
assert "ai_control_center_group_v1863m" in layout
assert "ai_control_center_active_panel_v1863m" in layout
assert "Kun valgt panel rendres" in layout
assert "Velg arbeids" in layout
assert "control_center_extra_panels_v18535" in app
assert "render_news_control_center_v18535" in app
assert "render_interactive_technical_control_center_v18535" in app
assert "render_market_ranking_control_center_v18535" in app
assert "render_watchlist_signals_control_center_v18535" in app
assert "render_system_admin_workspace(expanded=True)" in app
assert "render_top_picks_control_center_v1863s" in app
assert "render_ipo" in app
assert "render_paper_trading_dashboard" in app
assert "active_panel = None" in app
assert '"Normal visning": [AI_CONTROL_CENTER_MAIN_PANEL_LABEL_V18598]' not in layout
assert "Watchlist/varselkontroll er flyttet inn i AI Kontrollsenter" in app


