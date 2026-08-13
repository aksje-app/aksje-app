from __future__ import annotations


def test_build_label_accessor_matches_release():
    from app_version import APP_BUILD_LABEL, APP_VERSION, get_app_build_label

    assert get_app_build_label() == APP_BUILD_LABEL == APP_VERSION


def test_workspace_layout_import_chain_starts():
    import workspace_layout

    assert callable(workspace_layout.inject_workspace_css)


def test_application_requests_an_exported_build_label():
    import ast
    from pathlib import Path

    tree = ast.parse(Path("app.py").read_text(encoding="utf-8"))
    imports = {
        alias.name
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom) and node.module == "app_version"
        for alias in node.names
    }
    assert "get_app_build_label" in imports
    from app_version import get_app_build_label
    assert callable(get_app_build_label)
