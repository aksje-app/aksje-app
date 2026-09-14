from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace

import market_intelligence as mi
import scanner_worker as sw
import storage_retention as retention


def test_filename_uses_canonical_run_id_timestamp():
    run = {
        "run_id": "MI-20260903-222715",
        "created_at": "2026-09-03T20:27:16+00:00",
        "timezone_name": "Europe/Oslo",
        "job_name": "Obligatorisk kveldsrapport",
        "trigger": "SCHEDULED",
    }
    assert mi.safe_report_filename(run).endswith("20260903T222715.pdf")


def test_report_archive_separates_analysis_buys_and_source_issues(monkeypatch):
    monkeypatch.setattr(mi, "ensure_report_document", lambda run: {"metadata": {}, "sections": []})
    monkeypatch.setattr(mi, "section_payload", lambda doc, key, default=None: {
        "decision_overview": {"decision_ready_count": 0, "candidate_count": 1},
        "report_reliability": {"score": 58, "label": "LAV"},
        "quality_dimensions": {"report_decision_strength": 75},
    }.get(key, default))
    run = {
        "run_id": "MI-20260904-141712", "created_at": "2026-09-04T12:17:12+00:00",
        "job_name": "Obligatorisk ettermiddagsrapport", "trigger": "SCHEDULED",
        "summary": {"recommended": 18}, "candidates": [{"ticker": "NORAM.OL", "investment_score": 79.23}],
        "candidate_actionability": {"buy_ready_count": 0},
        "source_health": {"sources": [{"errors": 10}]}, "errors": [],
    }
    row = mi._archive_entry(run)
    assert row["analytical_recommended_count"] == 18
    assert row["buy_ready_count"] == 0
    assert row["error_count"] == 0
    assert row["source_issue_count"] == 10
    assert row["has_errors"] is False


def test_scanner_custom_watchlist_obeys_hard_limit(monkeypatch):
    monkeypatch.setattr(sw, "SCANNER_MAX_TICKERS", 3)
    monkeypatch.setenv("SCANNER_WATCHLIST", "AAPL,MSFT,NVDA,AMZN,META")
    monkeypatch.setattr(sw, "load_settings", lambda: {})
    monkeypatch.setattr(sw, "enabled_markets", lambda settings: ["USA"])
    assert sw.get_watchlist() == ["AAPL", "MSFT", "NVDA"]


def test_retention_applies_only_one_bounded_batch(monkeypatch):
    class FakeStorage:
        def __init__(self): self.deleted = []
        def health(self): return SimpleNamespace(to_dict=lambda: {"ok": True, "backend": "postgres"})
        def storage_usage_report(self): return {"database_bytes": 1000, "capacity_bytes": 5000}
        def list_json_names(self): return [f"operations/run_traces/{i:03d}.json" for i in range(230)]
        def list_jsonl_names(self): return []
        def delete_json(self, name): self.deleted.append(name)
    fake = FakeStorage()
    monkeypatch.setattr(retention, "get_storage_service", lambda: fake)
    monkeypatch.setattr(retention, "load_storage_retention_state", lambda: {})
    monkeypatch.setattr(retention, "_save_state", lambda state: state)
    monkeypatch.setenv("STORAGE_RETENTION_BATCH_SIZE", "7")
    result = retention.run_storage_retention(apply=True)
    assert result["state"] == "PARTIAL"
    assert result["deleted_this_batch"] == 7
    assert result["pending_after_batch"] == 43
    assert len(fake.deleted) == 7
    assert result["public_reports"]["state"] == "DEFERRED"


def test_required_report_grace_is_sixty_minutes(monkeypatch):
    monkeypatch.setattr(mi, "load_jobs", lambda: [])
    monkeypatch.setattr(mi, "load_job_history", lambda limit=2000: [])
    now = datetime(2026, 9, 4, 20, 45, tzinfo=timezone.utc)  # 22:45 Oslo
    ledger = mi.required_report_delivery_ledger(now)
    evening = next(row for row in ledger["rows"] if row["job_id"] == "MI-REQUIRED-EVENING")
    assert evening["status"] == "PÅGÅR"
    assert evening["grace_minutes"] == 60


def test_diagnostics_include_independent_retention_receipt():
    source = open("manual_job_background.py", encoding="utf-8").read()
    assert '"runtime/STORAGE_RETENTION.json"' in source


def test_scheduler_accepts_database_defer_without_status_one():
    source = open("scheduled_runner.py", encoding="utf-8").read()
    assert '"DEFERRED_DATABASE"' in source
    assert "PENDING_DATABASE_REPLAY" in source
