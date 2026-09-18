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


# Historisk kontrakt arkivert i tests/HISTORICAL_TEST_MANIFEST.json


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


def test_report_failure_sends_one_deduplicated_pushover_without_report_link(monkeypatch, tmp_path):
    receipts_path = tmp_path / "report_notification_receipts.json"
    monkeypatch.setattr(mi, "REPORT_NOTIFICATION_RECEIPTS_PATH", receipts_path)
    monkeypatch.setattr(mi, "_audit", lambda *args, **kwargs: None)
    receipts = {}
    monkeypatch.setattr(mi, "_read", lambda path, default: dict(receipts))
    monkeypatch.setattr(mi, "_write", lambda path, value: receipts.update(value))
    calls = []

    def send(message, **kwargs):
        calls.append((message, kwargs))
        return True, "sendt"

    monkeypatch.setitem(sys.modules, "notifier", types.SimpleNamespace(send_pushover_alert=send))
    monkeypatch.setattr("runtime_identity.runtime_label", lambda role="": "test-runtime")
    job = mi.JobProfile(
        job_id="MI-REQUIRED-MORNING",
        name="Obligatorisk morgenrapport",
        notification_mode="ALWAYS",
        notify_pushover=True,
    )
    run = {
        "run_id": "MI-FAIL-PUSH",
        "trigger": "SCHEDULED",
        "scheduled_for": "2026-09-18T06:00:00+00:00",
        "timezone_name": "Europe/Oslo",
        "suppress_notifications": False,
        "job_id": job.job_id,
        "job_name": job.name,
    }
    context = {
        "run_id": run["run_id"],
        "error_type": "ValueError",
        "error": "PDF/JSON-integritet feilet",
        "diagnostic_path": str(tmp_path / "MI-FAIL-PUSH_report_failure.json"),
    }

    first = mi.notify_report_failure(job, run, context)
    second = mi.notify_report_failure(job, run, context)

    assert first["sent"] is True
    assert first["attempted"] is True
    assert first["report_url"] == ""
    assert second == first
    assert len(calls) == 1
    message, kwargs = calls[0]
    assert "MANGLENDE FAST RAPPORT" in message
    assert "PDF: ikke bekreftet" in message
    assert "PDF/JSON-integritet feilet" in message
    assert "url" not in kwargs
    assert receipts["FAILURE:MI-FAIL-PUSH"]["status"] == "SENT"


def test_report_failure_notification_is_suppressed_for_silent_test(monkeypatch, tmp_path):
    monkeypatch.setattr(mi, "REPORT_NOTIFICATION_RECEIPTS_PATH", tmp_path / "receipts.json")
    monkeypatch.setattr(mi, "_audit", lambda *args, **kwargs: None)
    monkeypatch.setattr(mi, "_read", lambda path, default: {})
    monkeypatch.setattr(mi, "_write", lambda path, value: None)
    calls = []
    monkeypatch.setitem(
        sys.modules,
        "notifier",
        types.SimpleNamespace(send_pushover_alert=lambda *args, **kwargs: calls.append((args, kwargs))),
    )
    job = mi.JobProfile(name="Rapporttest", notify_pushover=True)
    receipt = mi.notify_report_failure(
        job,
        {"run_id": "MI-TEST-FAIL", "trigger": "TEST", "suppress_notifications": True},
        {"run_id": "MI-TEST-FAIL", "error_type": "ValueError", "error": "testfeil"},
    )

    assert receipt["attempted"] is False
    assert receipt["sent"] is False
    assert receipt["skipped_reason"] == "SUPPRESSED_TEST"
    assert calls == []


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
