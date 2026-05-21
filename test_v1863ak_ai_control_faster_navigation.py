from pathlib import Path
import py_compile


for name in ["app.py", "workspace_layout.py", "app_version.py"]:
    py_compile.compile(name, doraise=True)

app = Path("app.py").read_text(encoding="utf-8", errors="ignore")
layout = Path("workspace_layout.py").read_text(encoding="utf-8", errors="ignore")
version = Path("app_version.py").read_text(encoding="utf-8", errors="ignore")

assert 'APP_VERSION = "v18.6.3am"' in version
assert "_cc_fast_nav_v1863ak" in app
assert "render_live_market_banner()" in app
assert 'st.session_state["ai_control_center_group_v1863aj"] = selected_group' in layout
assert 'st.session_state["ai_control_center_active_panel_v1863aj"] = "" if selected_panel == "Ingen valgt" else selected_panel' in layout
assert "st.rerun()\n\n        active_label = st.session_state.get(\"ai_control_center_active_panel_v1863aj\")" not in layout
