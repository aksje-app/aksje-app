from __future__ import annotations

import importlib
from pathlib import Path

import app_version
import runtime_dependencies
from tools.check_runtime_dependencies import run_smoke

ROOT = Path(__file__).resolve().parents[1]


def test_version_contract_is_v19146():
    assert app_version.APP_VERSION == "v19.17.0-rc1"
    assert app_version.PREVIOUS_APP_VERSION == "v19.14.6"
    assert app_version.RANKING_MODEL_VERSION == "v19.16.0"
    assert app_version.AUTONOMY_POLICY_VERSION == "v19.16.0"


def test_pypdf_is_explicitly_pinned_in_requirements():
    requirements = (ROOT / "requirements.txt").read_text(encoding="utf-8").splitlines()
    assert "pypdf==5.9.0" in [line.strip() for line in requirements]


def test_runtime_dependency_check_reports_pypdf():
    result = runtime_dependencies.check_runtime_dependencies()
    assert result["ok"] is True
    assert result["checks"][0]["module"] == "pypdf"
    assert result["checks"][0]["available"] is True


def test_runtime_dependency_check_fails_closed(monkeypatch):
    original = importlib.import_module

    def fake_import(name: str, package=None):
        if name == "pypdf":
            raise ModuleNotFoundError("No module named 'pypdf'")
        return original(name, package)

    monkeypatch.setattr(runtime_dependencies.importlib, "import_module", fake_import)
    result = runtime_dependencies.check_runtime_dependencies()
    assert result["ok"] is False
    assert "pypdf" in result["errors"][0]
    try:
        runtime_dependencies.assert_runtime_dependencies()
    except RuntimeError as exc:
        assert "Runtime-avhengighetskontroll feilet" in str(exc)
    else:
        raise AssertionError("Manglende pypdf skulle blokkert oppstart")


def test_pdf_dependency_roundtrip_smoke():
    result = run_smoke()
    assert result["ok"] is True
    assert result["pdf_pages"] == 1
    assert result["pdf_size"] > 500
    assert result["marker_found"] is True


def test_web_scheduler_and_render_use_dependency_gate():
    app_source = (ROOT / "app.py").read_text(encoding="utf-8")
    scheduler_source = (ROOT / "scheduled_runner.py").read_text(encoding="utf-8")
    render_yaml = (ROOT / "render.yaml").read_text(encoding="utf-8")
    assert "check_runtime_dependencies" in app_source
    assert "assert_runtime_dependencies" in scheduler_source
    assert render_yaml.count("python tools/check_runtime_dependencies.py") == 2
