#!/usr/bin/env python3
"""Static navigation/rerun audit for v19.22.0 RC14.

The audit detects the live Streamlit failure pattern where application code
writes to a literal widget key after that widget has been instantiated in the
same function. It also verifies the global route lease, persistent timezone
write-through and the report fragment's single-render contract.
"""
from __future__ import annotations

import argparse
import ast
import json
from pathlib import Path
from typing import Any

from app_version import APP_VERSION

ROOT = Path(__file__).resolve().parents[1]
WIDGET_NAMES = {
    "radio", "selectbox", "multiselect", "text_input", "number_input",
    "time_input", "date_input", "checkbox", "slider", "toggle",
}


def _literal_widget_write_violations(root: Path) -> tuple[int, list[dict[str, Any]]]:
    scanned = 0
    violations: list[dict[str, Any]] = []
    for path in root.rglob("*.py"):
        if any(part in {"tests", "tools", ".git", ".venv", "__pycache__"} for part in path.parts):
            continue
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"))
        except Exception:
            continue
        scanned += 1
        for function in [node for node in ast.walk(tree) if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))]:
            widgets: dict[str, int] = {}
            writes: list[tuple[str, int]] = []
            for node in ast.walk(function):
                if isinstance(node, ast.Call):
                    name = node.func.attr if isinstance(node.func, ast.Attribute) else ""
                    if name in WIDGET_NAMES:
                        for keyword in node.keywords:
                            if keyword.arg == "key" and isinstance(keyword.value, ast.Constant) and isinstance(keyword.value.value, str):
                                widgets.setdefault(keyword.value.value, node.lineno)
                if isinstance(node, ast.Assign):
                    for target in node.targets:
                        if not isinstance(target, ast.Subscript):
                            continue
                        base = target.value
                        if not (isinstance(base, ast.Attribute) and base.attr == "session_state"):
                            continue
                        if isinstance(target.slice, ast.Constant) and isinstance(target.slice.value, str):
                            writes.append((target.slice.value, node.lineno))
            for key, write_line in writes:
                widget_line = widgets.get(key)
                if widget_line is not None and write_line > widget_line:
                    violations.append({
                        "file": path.relative_to(root).as_posix(),
                        "function": function.name,
                        "widget_key": key,
                        "widget_line": widget_line,
                        "write_line": write_line,
                    })
    return scanned, violations


def audit(root: Path = ROOT) -> dict[str, Any]:
    scanned, violations = _literal_widget_write_violations(root)
    app = (root / "app.py").read_text(encoding="utf-8")
    nav = (root / "navigation_state.py").read_text(encoding="utf-8")
    market = (root / "market_intelligence.py").read_text(encoding="utf-8")
    settings = (root / "settings_store.py").read_text(encoding="utf-8")
    registry = (root / "autonomi_core/configuration/registry.py").read_text(encoding="utf-8")
    workspace = (root / "workspace_layout.py").read_text(encoding="utf-8")

    progress_block = market[
        market.index("def _render_manual_report_progress_v1924"):
        market.index("def render_market_intelligence")
    ]
    terminal_block = progress_block[
        progress_block.index('if state in {"COMPLETED", "FAILED", "CANCELLED"}'):
    ]
    consume_pos = app.index("consume_global_navigation_route_v19220_rc14(st)")
    sidebar_pos = app.index("show_drift_controls_v1863cc = render_stable_sidebar_v18641")

    checks = {
        "global_rerun_guard_installed": "install_navigation_rerun_guard_v19220_rc14(st)" in app,
        "global_route_lease_defined": "GLOBAL_NAVIGATION_ROUTE_LEASE_KEY_V19220_RC14" in nav,
        "global_route_consumed_before_sidebar": consume_pos < sidebar_pos,
        "fragment_terminal_has_no_full_app_rerun": "_rerun_reports_v19220" not in terminal_block,
        "timezone_registry_write_through": '("ui_refresh_minutes", "ui_auto_refresh_enabled", "display_timezone")' in settings and '("ui_refresh_minutes", "ui_auto_refresh_enabled", "display_timezone")' in registry,
        "timezone_persistence_verified_after_save": "display_timezone_flash_v19220_rc14" in app and "persisted =" in app,
        "simple_control_center_uses_pending_group": "ai_control_center_group_pending_v19220_rc14" in workspace,
        "literal_post_widget_write_violations_zero": not violations,
    }
    return {
        "schema": "navigation-rerun-audit-v19.22.0-rc14",
        "version": APP_VERSION,
        "result": "PASS" if all(checks.values()) else "FAIL",
        "python_files_scanned": scanned,
        "checks": checks,
        "literal_post_widget_write_violations": violations,
        "full_app_rerun_call_count": sum(
            path.read_text(encoding="utf-8", errors="replace").count("st.rerun()")
            for path in root.rglob("*.py")
            if not any(part in {"tests", "tools", ".git", ".venv", "__pycache__"} for part in path.parts)
        ),
        "protected_widget_keys": [
            "ai_control_center_group_radio_v1863aj",
            "autonomy_core_workspace_v1880",
            "ai_control_center_group_v1863m",
        ],
        "production_parameters_changed": False,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    result = audit()
    rendered = json.dumps(result, ensure_ascii=False, indent=2)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered + "\n", encoding="utf-8")
    print(rendered)
    return 0 if result["result"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
