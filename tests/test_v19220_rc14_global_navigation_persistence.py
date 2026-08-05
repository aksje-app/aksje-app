from __future__ import annotations

import ast
from pathlib import Path

from navigation_state import (
    GLOBAL_NAVIGATION_ROUTE_LEASE_KEY_V19220_RC14,
    consume_global_navigation_route_v19220_rc14,
    install_navigation_rerun_guard_v19220_rc14,
)


class FakeStreamlit:
    def __init__(self):
        self.session_state = {
            "active_nav_target_v18674c": "system",
            "ai_control_center_group_v1863aj": "System",
            "ai_control_center_active_panel_v1863aj": "System/admin",
        }
        self.query_params = {
            "aa_nav": "system",
            "aa_group": "System",
            "aa_panel": "System/admin",
        }
        self.rerun_calls = []

    def rerun(self, *args, **kwargs):
        self.rerun_calls.append((args, kwargs))


def test_global_rerun_guard_queues_current_system_route_without_widget_writes():
    st = FakeStreamlit()
    assert install_navigation_rerun_guard_v19220_rc14(st) is True
    st.rerun()
    assert len(st.rerun_calls) == 1
    lease = st.session_state[GLOBAL_NAVIGATION_ROUTE_LEASE_KEY_V19220_RC14]
    assert lease["nav"] == "system"
    assert lease["group"] == "System"
    assert lease["panel"] == "System/admin"
    assert "ai_control_center_group_radio_v1863aj" not in st.session_state


def test_global_route_lease_is_consumed_before_widgets_and_keeps_system_admin():
    st = FakeStreamlit()
    install_navigation_rerun_guard_v19220_rc14(st)
    st.rerun()
    assert consume_global_navigation_route_v19220_rc14(st) is True
    assert GLOBAL_NAVIGATION_ROUTE_LEASE_KEY_V19220_RC14 not in st.session_state
    assert st.session_state["active_nav_target_v18674c"] == "system"
    assert st.session_state["ai_control_center_group_v1863aj"] == "System"
    assert st.session_state["ai_control_center_active_panel_v1863aj"] == "System/admin"
    lock = st.session_state["ai_control_center_route_lock_v19220_rc6"]
    assert lock["group"] == "System"
    assert lock["panel"] == "System/admin"
    assert st.query_params["aa_nav"] == "system"


def test_fragment_scope_rerun_is_not_promoted_to_global_route_lease():
    st = FakeStreamlit()
    install_navigation_rerun_guard_v19220_rc14(st)
    st.rerun(scope="fragment")
    assert len(st.rerun_calls) == 1
    assert GLOBAL_NAVIGATION_ROUTE_LEASE_KEY_V19220_RC14 not in st.session_state


def test_timezone_is_written_through_stable_reporting_ui_registry():
    settings_source = Path("settings_store.py").read_text(encoding="utf-8")
    registry_source = Path("autonomi_core/configuration/registry.py").read_text(encoding="utf-8")
    assert '("ui_refresh_minutes", "ui_auto_refresh_enabled", "display_timezone")' in settings_source
    assert '("ui_refresh_minutes", "ui_auto_refresh_enabled", "display_timezone")' in registry_source


def test_timezone_save_keeps_expander_open_and_verifies_persistence():
    source = Path("app.py").read_text(encoding="utf-8")
    block = source[source.index("def _render_display_time_settings_v19220_rc8"):source.index("def _render_runtime_diagnostics_v19220_rc8")]
    assert "display_time_settings_expanded_v19220_rc14" in block
    assert "display_timezone_flash_v19220_rc14" in block
    assert "persisted =" in block
    assert "st.rerun()" in block


def test_report_fragment_never_auto_reruns_whole_app_at_terminal_state():
    source = Path("market_intelligence.py").read_text(encoding="utf-8")
    block = source[source.index("def _render_manual_report_progress_v1924"):source.index("def render_market_intelligence")]
    terminal = block[block.index('if state in {"COMPLETED", "FAILED", "CANCELLED"}') :]
    assert "_rerun_reports_v19220" not in terminal
    assert "Ingen automatisk helsidererender" in terminal


def test_no_literal_session_state_write_occurs_after_same_literal_widget_key_in_function():
    """Static regression for the StreamlitAPIException pattern found live."""
    files = [p for p in Path(".").rglob("*.py") if "tests" not in p.parts and "tools" not in p.parts]
    widget_names = {
        "radio", "selectbox", "multiselect", "text_input", "number_input",
        "time_input", "date_input", "checkbox", "slider", "toggle",
    }
    violations = []
    for path in files:
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"))
        except Exception:
            continue
        for fn in [n for n in ast.walk(tree) if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))]:
            widgets: dict[str, int] = {}
            writes: list[tuple[str, int]] = []
            for node in ast.walk(fn):
                if isinstance(node, ast.Call):
                    name = node.func.attr if isinstance(node.func, ast.Attribute) else ""
                    if name in widget_names:
                        for kw in node.keywords:
                            if kw.arg == "key" and isinstance(kw.value, ast.Constant) and isinstance(kw.value.value, str):
                                widgets.setdefault(kw.value.value, node.lineno)
                if isinstance(node, ast.Assign):
                    for target in node.targets:
                        if not isinstance(target, ast.Subscript):
                            continue
                        value = target.value
                        if not (isinstance(value, ast.Attribute) and value.attr == "session_state"):
                            continue
                        if isinstance(target.slice, ast.Constant) and isinstance(target.slice.value, str):
                            writes.append((target.slice.value, node.lineno))
            for key, line in writes:
                if key in widgets and line > widgets[key]:
                    violations.append(f"{path}:{fn.name}:{key}:{widgets[key]}->{line}")
    assert violations == []
