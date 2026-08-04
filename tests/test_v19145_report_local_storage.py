from __future__ import annotations

import importlib
import json
import sys
import types
from pathlib import Path

import pytest

import app_version
import market_intelligence as mi
import trading_settings


def test_version_contract_is_v19145():
    assert app_version.APP_VERSION.startswith("v19.22.0-rc")
    assert app_version.PREVIOUS_APP_VERSION == "v19.22.0-rc7"
    assert app_version.RANKING_MODEL_VERSION == "v19.16.0"
    assert app_version.AUTONOMY_POLICY_VERSION == "v19.16.0"


def test_trading_rules_never_open_database_in_local_mode(monkeypatch):
    calls = []
    fake = types.SimpleNamespace(
        init_store=lambda: calls.append("init"),
        get_conn=lambda: calls.append("conn"),
        using_postgres=lambda: True,
    )
    monkeypatch.setitem(sys.modules, "paper_store", fake)
    monkeypatch.setenv("STORAGE_MODE", "local")
    monkeypatch.setenv("DATABASE_URL", "postgresql://must-not-be-used")

    assert trading_settings._load_from_db() is None
    assert trading_settings._save_to_db({"min_buy_score": 8}) is False
    assert calls == []


def test_trading_rules_never_open_database_without_database_url(monkeypatch):
    calls = []
    fake = types.SimpleNamespace(
        init_store=lambda: calls.append("init"),
        get_conn=lambda: calls.append("conn"),
        using_postgres=lambda: True,
    )
    monkeypatch.setitem(sys.modules, "paper_store", fake)
    monkeypatch.setenv("STORAGE_MODE", "auto")
    monkeypatch.delenv("DATABASE_URL", raising=False)

    assert trading_settings._load_from_db() is None
    assert trading_settings._save_to_db({"min_buy_score": 8}) is False
    assert calls == []


def test_report_storage_preflight_creates_and_verifies_paths(monkeypatch, tmp_path):
    root = tmp_path / "app_runtime" / "data" / "market_intelligence"
    monkeypatch.setattr(mi, "ROOT", root)
    monkeypatch.setattr(mi, "RUNS_DIR", root / "runs")
    monkeypatch.setattr(mi, "SUMMARIES_DIR", root / "summaries")
    monkeypatch.setenv("APP_RUNTIME_ROOT", str(tmp_path / "app_runtime"))
    monkeypatch.setenv("STORAGE_MODE", "local")

    report_path = root / "summaries" / "smoke.pdf"
    result = mi.report_storage_preflight("MI-SMOKE", report_path)

    assert result["ok"] is True
    assert result["storage_mode"] == "local"
    assert result["report_path"] == str(report_path)
    assert all(item["writable"] for item in result["checks"])
    assert (root / "runs").is_dir()
    assert (root / "summaries").is_dir()
    assert not list(root.rglob(".report_write_probe_*.tmp"))


def test_report_storage_preflight_reports_exact_unwritable_path(monkeypatch, tmp_path):
    blocker = tmp_path / "not-a-directory"
    blocker.write_text("blocked", encoding="utf-8")
    impossible = blocker / "market_intelligence"
    monkeypatch.setattr(mi, "ROOT", impossible)
    monkeypatch.setattr(mi, "RUNS_DIR", impossible / "runs")
    monkeypatch.setattr(mi, "SUMMARIES_DIR", impossible / "summaries")

    with pytest.raises(PermissionError) as caught:
        mi.report_storage_preflight("MI-FAIL", impossible / "summaries" / "x.pdf")
    assert str(impossible) in str(caught.value)


def test_report_failure_is_persisted_with_traceback_and_path(monkeypatch, tmp_path):
    monkeypatch.setattr(mi, "REPORT_FAILURES_DIR", tmp_path / "logs" / "report_failures")
    monkeypatch.setattr(mi, "_audit", lambda *args, **kwargs: None)
    report_path = tmp_path / "reports" / "failed.pdf"

    try:
        raise ValueError("syntetisk PDF-feil")
    except ValueError as exc:
        payload = mi.record_report_failure("MI-TRACE", report_path, exc)

    assert payload["error_type"] == "ValueError"
    assert payload["report_path"] == str(report_path)
    assert "syntetisk PDF-feil" in payload["traceback"]
    diagnostic = Path(payload["diagnostic_path"])
    assert diagnostic.is_file()
    stored = json.loads(diagnostic.read_text(encoding="utf-8"))
    assert stored["run_id"] == "MI-TRACE"
    assert stored["stage"] == "REPORT"
    assert stored["report_path"] == str(report_path)


def test_invalid_starlette_option_is_removed():
    config = Path(".streamlit/config.toml").read_text(encoding="utf-8")
    env = Path(".env.example").read_text(encoding="utf-8")
    render = Path("render.yaml").read_text(encoding="utf-8")
    assert "useStarlette" not in config
    assert "STREAMLIT_SERVER_USE_STARLETTE" not in env
    assert "STREAMLIT_SERVER_USE_STARLETTE" not in render


def test_autonomy_ui_exposes_report_error_details():
    source = Path("autonomous_orchestrator_ui.py").read_text(encoding="utf-8")
    for field in ("error_stage", "error_type", "report_path", "diagnostic_path", "error_trace"):
        assert field in source
