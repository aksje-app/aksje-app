from __future__ import annotations

import io
import json
import sys
from datetime import datetime, timezone
from types import SimpleNamespace
from zipfile import ZipFile

import manual_job_background as background
import market_intelligence as mi
import report_system_check as system_check


def _notification_run(*, automatic: bool) -> dict:
    return {
        "run_id": "MI-RC1631-SERIES",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "trigger": "SCHEDULED_REPORT_TEST_NOTIFICATION" if automatic else "MANUAL_REPORT_TEST_NOTIFICATION",
        "test_run": True,
        "suppress_notifications": False,
        "markets": ["Norge", "Sverige", "USA"],
        "summary": {"deep_analyzed": 10, "recommended": 0},
        "changes": {"new": [], "improved": []},
        "report_status": {"label": "UTKAST – IKKE ENDELIG"},
        "report_revision": {"revision_label": "R1"},
        "candidates": [],
        "proposals": [],
        "report_test_series": {
            "series_id": "RTS-20260809-TEST01" if automatic else "",
            "part": 2 if automatic else 0,
            "total": 4 if automatic else 0,
            "attempt": 2 if automatic else 0,
            "automatic": automatic,
        },
    }


def test_automatic_notification_contains_series_and_part(monkeypatch):
    captured = {}
    monkeypatch.setattr(mi, "_read", lambda *args, **kwargs: {})
    monkeypatch.setattr(mi, "_write", lambda *args, **kwargs: None)
    monkeypatch.setattr(mi, "_audit", lambda *args, **kwargs: None)
    monkeypatch.setitem(sys.modules, "notifier", SimpleNamespace(
        send_pushover_alert=lambda message, title="", **kwargs: (captured.update(message=message, title=title) or True, None),
    ))
    job = mi.JobProfile(name="Autonomi rapporttest", notification_mode="ALWAYS", notify_only_changes=False)
    ok, _ = mi._notification(job, _notification_run(automatic=True))
    assert ok is True
    assert "AUTOMATISK 2/4" in captured["title"]
    assert "AUTOMATISK RAPPORTTEST 2/4" in captured["message"]
    assert "RTS-20260809-TEST01" in captured["message"]


def test_manual_notification_is_explicitly_not_part_of_series(monkeypatch):
    captured = {}
    monkeypatch.setattr(mi, "_read", lambda *args, **kwargs: {})
    monkeypatch.setattr(mi, "_write", lambda *args, **kwargs: None)
    monkeypatch.setattr(mi, "_audit", lambda *args, **kwargs: None)
    monkeypatch.setitem(sys.modules, "notifier", SimpleNamespace(
        send_pushover_alert=lambda message, title="", **kwargs: (captured.update(message=message, title=title) or True, None),
    ))
    job = mi.JobProfile(name="Autonomi rapporttest", notification_mode="ALWAYS", notify_only_changes=False)
    ok, _ = mi._notification(job, _notification_run(automatic=False))
    assert ok is True
    assert "MANUELL TEST" in captured["title"]
    assert "teller ikke i automatisk 1/4–4/4" in captured["message"]


def test_fast_system_check_runs_without_market_pipeline(monkeypatch):
    memory = {}
    monkeypatch.setattr(system_check, "write_json", lambda key, path, value: memory.update(dict(value)))
    monkeypatch.setattr(system_check, "read_json", lambda key, path, default: dict(memory or default))
    monkeypatch.setenv("RENDER_EXTERNAL_URL", "https://aksje-app.onrender.com")
    monkeypatch.setitem(sys.modules, "notifier", SimpleNamespace(send_pushover_alert=lambda *args, **kwargs: (True, None)))

    result = system_check.run_report_system_check(send_notification=True)
    assert result["state"] == "PASS"
    assert result["safe_scope"] == "NO_MARKET_SCAN_NO_PORTFOLIO_ACTION_NO_LEARNING_ACTION"
    assert {row["name"] for row in result["checks"]} == {
        "Varig database", "Rapportlås", "PDF-motor", "Offentlig rapportlenke", "Pushover",
    }


def test_diagnostic_bundle_contains_timeline_system_check_and_pushover_audit(monkeypatch):
    monkeypatch.setattr(background, "get_status", lambda *_: {"execution_id": "MBJ-RC1631", "state": "FAILED"})
    monkeypatch.setitem(sys.modules, "learning_acceptance", SimpleNamespace(build_learning_diagnostics=lambda: {"acceptance": {}}))
    monkeypatch.setitem(
        sys.modules,
        "report_test_mode",
        SimpleNamespace(load_report_test_mode=lambda: {"series_id": "RTS-DIAG", "timeline": [{"event": "AUTOMATIC_TEST_STARTED"}]}),
    )
    monkeypatch.setitem(sys.modules, "report_system_check", SimpleNamespace(load_report_system_check=lambda: {"state": "PASS"}))
    monkeypatch.setitem(sys.modules, "notifier", SimpleNamespace(pushover_audit=lambda limit=50: [{"title": "AUTOMATISK 1/4", "success": True}]))
    monkeypatch.setitem(sys.modules, "scheduled_runner", SimpleNamespace(load_unattended_state=lambda: {"state": "COMPLETED"}))

    payload, _ = background.diagnostic_bundle("MBJ-RC1631")
    with ZipFile(io.BytesIO(payload)) as archive:
        names = set(archive.namelist())
        assert "scheduler/REPORT_TEST_TIMELINE.json" in names
        assert "scheduler/REPORT_SYSTEM_CHECK.json" in names
        assert "notifications/PUSHOVER_AUDIT.json" in names
        assert json.loads(archive.read("scheduler/REPORT_TEST_TIMELINE.json"))[0]["event"] == "AUTOMATIC_TEST_STARTED"
