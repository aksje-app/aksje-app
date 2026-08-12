from __future__ import annotations
from datetime import date, datetime, timezone
import app_version
import autonomous_decision_reduction as adr
import market_intelligence as mi
import paper_scanner_runtime as psr
import report_channel_consistency as rcc

def test_release_version_is_rc1631c():
    assert app_version.APP_VERSION == "v19.22.0-rc16.31c"
    assert app_version.PREVIOUS_APP_VERSION == "v19.22.0-rc16.31b"

def test_required_job_ignores_even_corrupt_scan_windows():
    job = mi.JobProfile(job_id="MI-REQUIRED-MORNING", name="Obligatorisk morgenrapport",
                        schedules=["08:00"], scan_windows=[{"start":"08:00","end":"12:00","interval_minutes":30}])
    assert [slot.strftime("%H:%M") for slot in mi._localized_slot(job, date(2026, 8, 13))] == ["08:00"]

def test_review_top3_is_not_restricted_to_buys():
    candidates = [
        {"ticker":"AAA", "investment_score":77, "risk_score":20, "portfolio_action":"WATCH"},
        {"ticker":"BBB", "investment_score":75, "risk_score":20, "portfolio_action":"WATCH"},
        {"ticker":"CCC", "investment_score":73, "risk_score":20, "portfolio_action":"WATCH"},
    ]
    rows, summary = adr.apply_decision_reduction(candidates, threshold=90)
    assert len(rows) == 3
    assert [row["ticker"] for row in summary["priority_top3"]] == ["AAA", "BBB", "CCC"]

def test_channel_projection_exposes_review_ranking():
    run = {"priority_top3":[{"ticker":"AAA","investment_score":77,"autonomy_outcome_label":"Overvåkes automatisk"}],
           "report_document":{"metadata":{"report_id":"R1"},"sections":[]}}
    projection = rcc.projection_from_run(run)
    assert projection["ranking"] == []
    assert projection["review_ranking"][0]["ticker"] == "AAA"

def test_stale_paper_worker_detection(monkeypatch):
    monkeypatch.setattr(psr, "load_scanner_status", lambda: {"heartbeat_at":"2026-07-25T23:00:00+00:00"})
    assert psr.scanner_worker_is_stale(45) is True
