from __future__ import annotations

from datetime import datetime, timedelta, timezone
from io import BytesIO

from pypdf import PdfReader

import market_intelligence as mi
import public_report_store as prs
import storage_retention as retention
from services.storage_service import StorageService


def _candidate(ticker: str, score: float, outcome: str) -> dict:
    return {
        "ticker": ticker, "market": "USA", "investment_score": score,
        "risk_score": 35, "portfolio_action": "WATCH",
        "autonomy_outcome_label": outcome,
        "autonomy_outcome_reason": "Ikke kjøpsgodkjent; følges automatisk.",
        "blockers": ["Evidensporten er ikke fullført"],
        "status": "OVERVÅKES", "valid_for_decision": True,
        "evidence_valid_for_decision": False,
    }


def _run() -> dict:
    candidates = [
        _candidate("AMGN", 72.08, "Overvåkes automatisk"),
        _candidate("APA", 71.34, "Undersøkes manuelt"),
        _candidate("ANET", 69.53, "Automatisk avvist"),
    ]
    priority = [{**row, "priority_rank": index} for index, row in enumerate(candidates, 1)]
    return {
        "run_id": "MI-RC31D", "created_at": "2026-08-13T06:01:30+00:00",
        "scheduled_for": "2026-08-13T08:00:00+02:00", "timezone_name": "Europe/Oslo",
        "job_id": "MI-REQUIRED-MORNING", "job_name": "Obligatorisk morgenrapport",
        "trigger": "SCHEDULED", "markets": ["Norge", "Sverige", "USA"],
        "summary": {"scanned": 75, "deep_analyzed": 10, "recommended": 0},
        "candidates": candidates, "priority_top3": priority,
        "autonomous_decision_reduction": {"priority_top3": priority},
        "report_summary": {"deep_analyzed": 10, "decision_ready": 0, "automatic_watch": 1,
                           "manual_review": 1, "evidence_data_ready": 0},
        "data_quality": {"score": 100, "label": "UTMERKET"},
        "changes": {}, "errors": [], "warnings": [],
    }


def test_pdf_shows_review_order_without_fabricating_buys():
    reader = PdfReader(BytesIO(mi.build_pdf(_run())))
    pages = [page.extract_text() or "" for page in reader.pages]
    first = pages[0]
    assert "Prioritert vurderingsrekkefølge 1-3" in first
    assert all(ticker in first for ticker in ("AMGN", "APA", "ANET"))
    assert "Kjøpsgodkjent" in first
    assert "0 kjøpskandidat(er)" in first
    assert "ikke en kjøpsanbefaling" in first
    assert not any((page.strip().startswith("Vurderinger utløper") and len(page.splitlines()) < 8) for page in pages)


def test_actual_style_report_is_six_pages_without_blank_page():
    run = _run()
    run["candidates"] += [
        _candidate(f"TEST{index}", 68 - index, "Automatisk avvist")
        for index in range(4, 11)
    ]
    pdf = mi.build_pdf(run)
    pages = [page.extract_text() or "" for page in PdfReader(BytesIO(pdf)).pages]
    assert len(pages) <= 6
    assert all(len(page.strip().splitlines()) >= 8 for page in pages)


def test_public_report_retention_removes_expired_payload(monkeypatch, tmp_path):
    storage = StorageService(base_dir=tmp_path, mode="local")
    now = datetime(2026, 8, 13, tzinfo=timezone.utc)
    old = now - timedelta(hours=1)
    valid = now + timedelta(hours=1)
    index = [
        {"token": "A" * 32, "expires_at": old.isoformat(), "report_id": "OLD"},
        {"token": "B" * 32, "expires_at": valid.isoformat(), "report_id": "LIVE"},
    ]
    storage.write_json(prs.INDEX_KEY, index)
    storage.write_json(f"public_reports/{'A' * 32}.json", {"token": "A" * 32})
    storage.write_json(f"public_reports/{'B' * 32}.json", {"token": "B" * 32})
    monkeypatch.setattr(prs, "get_storage_service", lambda: storage)
    monkeypatch.setattr(prs, "INDEX_PATH", tmp_path / "public_reports/index.json")
    result = prs.prune_expired_public_reports(now=now)
    assert result == {"deleted_payloads": 1, "retained_links": 1}
    assert not storage.read_json(f"public_reports/{'A' * 32}.json", {})
    assert storage.read_json(f"public_reports/{'B' * 32}.json", {})


def test_retention_policy_never_targets_protected_ledgers():
    protected_words = ("portfolio", "trade", "position", "decision", "settings", "audit")
    assert not any(any(word in prefix.lower() for word in protected_words) for prefix in retention.KV_LIMITS)
