from __future__ import annotations

import io
import json
import sys
from datetime import datetime, timezone
from types import SimpleNamespace
from zipfile import ZipFile

import cron_control
import manual_job_background as background
import market_hours
import scanner_worker as sw


def test_market_calendar_can_be_scoped_to_three_automated_markets(monkeypatch):
    monkeypatch.setattr(
        market_hours,
        "market_status",
        lambda market: {"is_open": market in {"USA", "BRASIL"}, "label": market},
    )
    assert market_hours.open_markets(("USA", "NORGE", "SVERIGE")) == ["USA"]
    assert market_hours.market_status_lines(("USA", "NORGE", "SVERIGE")) == [
        "USA", "NORGE", "SVERIGE",
    ]


def test_paper_scanner_filters_non_core_markets_even_when_open(monkeypatch):
    monkeypatch.setattr(sw, "open_markets", lambda markets=None: ["USA", "BRASIL"])
    assert sw._open_automated_markets() == ["USA"]

    monkeypatch.setenv("SCANNER_WATCHLIST", "AAPL,PETR4.SA,AKER.OL,ATCO-A.ST")
    monkeypatch.setattr(
        sw,
        "load_settings",
        lambda: {"markets": {"USA": True, "NORGE": True, "SVERIGE": True, "BRASIL": True}},
    )
    monkeypatch.setattr(sw, "enabled_markets", lambda settings: [key for key, value in settings["markets"].items() if value])
    assert sw.get_watchlist() == ["AAPL", "AKER.OL", "ATCO-A.ST"]


def test_cooldown_uses_completion_not_start(monkeypatch):
    saved = {
        "background_scanning_enabled": True,
        "scan_interval_minutes": 15,
        "last_scan_completed_at": "2026-08-27T18:21:55+00:00",
        "last_scan_started_at": "2026-08-27T17:57:53+00:00",
    }
    monkeypatch.setattr(cron_control, "load_settings", lambda: dict(saved))
    monkeypatch.setattr(
        cron_control,
        "_utc_now",
        lambda: datetime(2026, 8, 27, 18, 25, 14, tzinfo=timezone.utc),
    )
    allowed, reason = cron_control.should_run_background_scan()
    assert allowed is False
    assert "3.3 min siden" in reason


def test_completion_marker_preserves_start_and_sets_terminal_cooldown(monkeypatch):
    settings = {"last_scan_started_at": "2026-08-27T17:57:53+00:00"}
    monkeypatch.setattr(cron_control, "load_settings", lambda: dict(settings))
    monkeypatch.setattr(cron_control, "save_settings", lambda value: settings.update(value))
    monkeypatch.setattr(
        cron_control,
        "_utc_now",
        lambda: datetime(2026, 8, 27, 18, 21, 55, tzinfo=timezone.utc),
    )
    cron_control.mark_background_scan_completed("COMPLETED")
    assert settings["last_scan_started_at"] == "2026-08-27T17:57:53+00:00"
    assert settings["last_scan_completed_at"] == "2026-08-27T18:21:55+00:00"
    assert settings["last_scan_outcome"] == "COMPLETED"


def test_memory_gate_explains_exact_trigger():
    healthy = sw.scanner_memory_decision(
        {"cgroup_memory_current_mb": 648.8, "cgroup_memory_limit_mb": 2048.0,
         "cgroup_memory_headroom_mb": 1399.2, "process_rss_mb": 540.0},
        soft_limit_mb=1700,
    )
    assert healthy["pressure"] is False
    assert healthy["reason"] == "NONE"

    headroom = sw.scanner_memory_decision(
        {"cgroup_memory_current_mb": 648.8, "cgroup_memory_limit_mb": 700.0,
         "cgroup_memory_headroom_mb": 51.2},
        soft_limit_mb=1700,
    )
    assert headroom["pressure"] is True
    assert headroom["reason"] == "CGROUP_HEADROOM"

    both = sw.scanner_memory_decision(
        {"cgroup_memory_current_mb": 1750.0, "cgroup_memory_limit_mb": 1800.0,
         "cgroup_memory_headroom_mb": 50.0},
        soft_limit_mb=1700,
    )
    assert both["reason"] == "SOFT_LIMIT+CGROUP_HEADROOM"


def test_diagnostic_bundle_contains_current_scanner_evidence_without_payload(monkeypatch):
    monkeypatch.setattr(background, "get_status", lambda *_: {"execution_id": "MBJ-AS", "state": "COMPLETED"})
    monkeypatch.setitem(sys.modules, "learning_acceptance", SimpleNamespace(build_learning_diagnostics=lambda: {"acceptance": {}}))
    monkeypatch.setitem(sys.modules, "report_test_mode", SimpleNamespace(load_report_test_mode=lambda: {}))
    monkeypatch.setitem(sys.modules, "report_system_check", SimpleNamespace(load_report_system_check=lambda: {}))
    monkeypatch.setitem(sys.modules, "notifier", SimpleNamespace(pushover_audit=lambda limit=50: []))
    monkeypatch.setitem(sys.modules, "scheduled_runner", SimpleNamespace(load_unattended_state=lambda: {
        "state": "PARTIAL_CHECKPOINT", "paper_scanner": {"state": "PARTIAL_CHECKPOINT"},
    }))
    monkeypatch.setitem(sys.modules, "execution_coordination", SimpleNamespace(report_execution_owner=lambda: {}))
    monkeypatch.setitem(sys.modules, "runtime_identity", SimpleNamespace(runtime_identity_snapshot=lambda: {}))
    monkeypatch.setitem(sys.modules, "runtime_memory", SimpleNamespace(memory_snapshot=lambda: {"cgroup_memory_limit_mb": 2048.0}))
    monkeypatch.setitem(sys.modules, "paper_scanner_runtime", SimpleNamespace(
        load_scanner_status=lambda: {
            "state": "PARTIAL_CHECKPOINT", "memory_pressure_reason": "CGROUP_HEADROOM",
            "memory_policy": {"configured_soft_limit_mb": 1700.0}, "api_key": "MUST-NOT-LEAK",
        },
        load_scanner_checkpoint=lambda: {
            "scan_run_id": "SCAN-AS", "tickers": ["AAPL", "MSFT"], "next_index": 1,
            "candidate_snapshots": [{"private_payload": "MUST-NOT-LEAK"}], "latest_prices": {"AAPL": 1},
        },
    ))

    payload, _ = background.diagnostic_bundle("MBJ-AS")
    with ZipFile(io.BytesIO(payload)) as archive:
        names = set(archive.namelist())
        assert "scanner/PAPER_SCANNER_STATUS.json" in names
        assert "scanner/PAPER_SCANNER_CHECKPOINT.json" in names
        assert "scanner/SCANNER_CONFIGURATION.json" in names
        status = json.loads(archive.read("scanner/PAPER_SCANNER_STATUS.json"))
        checkpoint = json.loads(archive.read("scanner/PAPER_SCANNER_CHECKPOINT.json"))
    assert status["memory_pressure_reason"] == "CGROUP_HEADROOM"
    assert checkpoint["candidate_count"] == 1
    assert "candidate_snapshots" not in checkpoint
    assert b"MUST-NOT-LEAK" not in payload
