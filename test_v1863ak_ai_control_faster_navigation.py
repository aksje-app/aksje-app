from pathlib import Path
import py_compile


for name in ["app.py", "workspace_layout.py", "app_version.py"]:
    py_compile.compile(name, doraise=True)

app = Path("app.py").read_text(encoding="utf-8", errors="ignore")
layout = Path("workspace_layout.py").read_text(encoding="utf-8", errors="ignore")
version = Path("app_version.py").read_text(encoding="utf-8", errors="ignore")

assert 'APP_VERSION = "v18.6.3ba"' in version
assert "_cc_fast_nav_v1863ak" in app
assert "render_live_market_banner()" in app
startup_marker_pos = app.find("startup_heavy_update_pending_v1863an")
startup_clear_pos = app.find("_clear_startup_heavy_update_for_control_center_v1863an()", startup_marker_pos)
control_center_pos = app.find("render_ai_control_center(extra_panels=control_center_extra_panels_v18535())")
assert 0 < startup_marker_pos < startup_clear_pos < control_center_pos
assert 'st.session_state["heavy_update_allowed_v148"] = False' in app
assert "_finish_control_center_render_cycle_v1863ax()" in app
assert app.find("_finish_control_center_render_cycle_v1863ax()", control_center_pos) < app.find("st.stop()", control_center_pos)
assert 'st.session_state["ai_control_center_group_v1863aj"] = selected_group' in layout
assert 'st.session_state["ai_control_center_active_panel_v1863aj"] = "" if selected_panel == "Ingen valgt" else selected_panel' in layout
assert "st.rerun()\n\n        active_label = st.session_state.get(\"ai_control_center_active_panel_v1863aj\")" not in layout


