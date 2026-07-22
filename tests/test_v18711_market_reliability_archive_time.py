from datetime import datetime, timezone

import investment_pipeline as ip
import market_intelligence as mi
from local_time import as_local, local_display


def test_builtin_universe_precedes_stale_persisted_rows():
    primary = [{"ticker": "AAPL", "market": "USA", "source_path": "/opt/render/project/stale.json"}]
    fallback = [{"ticker": "MSFT", "market": "USA"}, {"ticker": "NVDA", "market": "USA"}]
    rows = ip._merge_candidate_rows(primary, fallback, "USA", 2)
    assert [row["ticker"] for row in rows] == ["MSFT", "NVDA"]
    assert all("source_path" not in row for row in rows)


def test_market_failure_reduces_quality_and_names_market():
    refresh = {"live_count": 250, "cache_count": 0, "error_count": 0, "latest_trade_dates": ["2026-07-20"]}
    diagnostics = [
        {"market": "USA", "scanned": 0, "status": "FEIL: MARKEDSKJØRING"},
        {"market": "Norge", "scanned": 50, "status": "OK"},
    ]
    quality = mi.build_data_quality(refresh, 250, diagnostics, ["USA", "Norge"])
    assert quality["score"] < 90
    assert quality["label"] != "UTMERKET"
    assert quality["failed_markets"] == ["USA"]


def test_archive_verification_requires_both_run_and_archive(monkeypatch):
    monkeypatch.setattr(mi, "load_run", lambda run_id: {"run_id": run_id})
    monkeypatch.setattr(mi, "_load_report_archive", lambda: [])
    assert mi.verify_report_persistence("MI-1")["ok"] is False
    monkeypatch.setattr(mi, "_load_report_archive", lambda: [{"run_id": "MI-1"}])
    assert mi.verify_report_persistence("MI-1")["ok"] is True


def test_oslo_timezone_handles_summer_time_and_scheduler():
    utc = datetime(2026, 7, 20, 19, 50, tzinfo=timezone.utc)
    local = as_local(utc, "Europe/Oslo")
    assert (local.hour, local.minute) == (21, 50)
    assert "Europe/Oslo" in local_display(utc, "Europe/Oslo")
    job = mi.JobProfile(name="Tid", enabled=True, schedules=["21:50"], weekdays=[0], timezone_name="Europe/Oslo")
    assert mi._slot_due(job, utc) is True


def test_insider_coverage_distinguishes_diagnostic_states():
    candidates = []
    for ticker, coverage in [("A", "AVAILABLE"), ("B", "DISCOVERY_ONLY"), ("C", "NOT_CONFIGURED"), ("D", "ERROR"), ("E", "MISSING")]:
        candidates.append({"ticker": ticker, "market": "Norge", "raw": {"insider_intelligence": {"coverage": coverage}}})
    row = mi.insider_coverage_by_market(candidates)[0]
    assert (row["verified"], row["discovery"], row["not_configured"], row["source_errors"], row["missing"]) == (1, 1, 1, 1, 1)
