from __future__ import annotations

import sys
import types
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import market_intelligence as mi


def test_schedule_timeline_detects_missed_morning_run_in_oslo():
    job = mi.JobProfile(
        name="Morgenanalyse",
        schedules=["08:30", "22:30"],
        weekdays=[0, 1, 2, 3, 4],
        timezone_name="Europe/Oslo",
        last_run_at="2026-07-23T20:33:35+00:00",
        enabled=True,
    )
    now = datetime(2026, 7, 24, 6, 41, tzinfo=timezone.utc)  # 08:41 Europe/Oslo
    timeline = mi.schedule_timeline(job, now)
    assert timeline["missed"] is True
    assert timeline["last_planned_status"] == "Ikke startet"
    assert timeline["previous_planned_utc"].startswith("2026-07-24T06:30")
    assert timeline["next_planned_utc"].startswith("2026-07-24T20:30")


def test_schedule_timeline_marks_completed_when_last_run_after_planned_slot():
    job = mi.JobProfile(
        name="Morgenanalyse",
        schedules=["08:30", "22:30"],
        weekdays=[0, 1, 2, 3, 4],
        timezone_name="Europe/Oslo",
        last_run_at="2026-07-24T06:33:00+00:00",
        enabled=True,
    )
    now = datetime(2026, 7, 24, 6, 41, tzinfo=timezone.utc)
    timeline = mi.schedule_timeline(job, now)
    assert timeline["missed"] is False
    assert timeline["last_planned_status"] == "Fullført"


def test_test_without_notification_never_imports_or_sends_pushover(monkeypatch):
    job = mi.JobProfile(name="Morgenanalyse", job_id="MIJ-TEST")
    with patch.object(mi, "_read", return_value={}), patch.object(mi, "_write") as write, patch.object(mi, "_audit"):
        ok, detail = mi._notification(
            job,
            {
                "run_id": "MI-TEST-NO-PUSH",
                "trigger": "MANUAL_DRAFT_TEST",
                "test_run": True,
                "suppress_notifications": True,
            },
        )
    assert ok is False
    assert "Test uten varsling" in detail
    assert write.called


def test_test_with_pushover_is_labeled_as_test(monkeypatch):
    sent = {}

    def fake_send(message, title="", url=None, url_title=None):
        sent["message"] = message
        sent["title"] = title
        sent["url"] = url
        sent["url_title"] = url_title
        return True, "Sendt"

    monkeypatch.setitem(sys.modules, "notifier", types.SimpleNamespace(send_pushover_alert=fake_send))
    job = mi.JobProfile(name="Morgenanalyse", job_id="MIJ-TEST")
    with patch.object(mi, "_read", return_value={}), patch.object(mi, "_write"), patch.object(mi, "_audit"):
        ok, detail = mi._notification(
            job,
            {
                "run_id": "MI-TEST-PUSH",
                "trigger": "MANUAL_DRAFT_TEST_NOTIFICATION",
                "test_run": True,
                "suppress_notifications": False,
                "markets": ["Norge"],
                "summary": {"deep_analyzed": 1, "recommended": 0},
                "changes": {"new": [], "improved": []},
                "candidates": [],
            },
        )
    assert ok is True
    assert detail.startswith("Sendt")
    assert "TESTVARSEL" in sent["title"]
    assert "TESTVARSEL" in sent["message"]


def test_plain_text_export_and_ascii_filename_are_available():
    run = {
        "run_id": "MI-1",
        "created_at": "2026-07-24T06:41:00+00:00",
        "timezone_name": "Europe/Oslo",
        "job_name": "Morgenanalyse ØÅ",
        "trigger": "SCHEDULED",
        "markets": ["Norge"],
        "summary": {"scanned": 25, "deep_analyzed": 10, "proposals": 3, "recommended": 1},
        "data_quality": {"score": 94, "label": "GODT"},
        "notification": {"status_label": "Sendt"},
        "candidates": [{"rank": 1, "ticker": "EQNR", "market": "Norge", "investment_score": 82.5, "portfolio_action": "BUY"}],
    }
    text = mi.build_text_report(run)
    assert "Morgenrapport" in text
    assert "Pushover: Sendt" in text
    assert "EQNR" in text
    filename = mi.safe_ascii_report_filename(run, "txt")
    assert filename.endswith(".txt")
    assert filename.isascii()
    assert "Ø" not in filename and "Å" not in filename


def test_job_ui_contains_progress_bar_and_safe_test_buttons():
    source = (ROOT / "market_intelligence.py").read_text(encoding="utf-8")
    assert "st.progress(0, text=\"Klargjør testkjøring\")" in source
    assert "Test uten varsling" in source
    assert "Test med Pushover" in source
    assert "send_notifications=bool(send_push)" in source
    assert "Kjør manglende rapport nå" in source
    assert "Last ned rapport som tekst" in source
