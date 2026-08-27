from __future__ import annotations

import json
from pathlib import Path

import market_intelligence as mi
from app_version import APP_VERSION
from autonomous_decision_reduction import (
    OUTCOME_MODERATE_BUY,
    apply_decision_reduction,
)
from autonomous_portfolio import production_buy_authorization
from market_intelligence import build_main_pdf, build_technical_pdf, build_text_report
from report_export_audit import canonical_public_run, validate_artifacts


ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "tests" / "HISTORICAL_TEST_MANIFEST.json"


def _candidate(ticker: str, score: float, *, action: str = "REVIEW") -> dict:
    return {
        "ticker": ticker,
        "market": "Norge" if ticker.endswith(".OL") else "USA",
        "investment_score": score,
        "risk_score": 30.0,
        "valid_for_decision": True,
        "evidence_valid_for_decision": True,
        "mission_eligible": True,
        "analysis_stage": "EVIDENCE_CONTROLLED",
        "portfolio_action": action,
        "portfolio_decision": {"existing_position": False, "blockers": []},
        "decision_readiness": {
            "news": "VERIFIED_FACTS_FOUND",
            "insider": "CHECKED_NO_EVENTS",
            "conflicts": 0,
        },
        "raw": {},
    }


def _canonical_run() -> dict:
    rows, reduction = apply_decision_reduction(
        [_candidate("BMY", 71.4), _candidate("WAWI.OL", 70.9)],
        threshold=73.0,
        near_threshold_gap=6.0,
        maximum_risk=65.0,
    )
    return canonical_public_run({
        "run_id": "MI-RC16-31AQ-CURRENT-CONTRACT",
        "created_at": "2026-08-27T14:00:00+00:00",
        "timezone_name": "Europe/Oslo",
        "job_id": "MI-REQUIRED-AFTERNOON",
        "job_name": "Obligatorisk ettermiddagsrapport",
        "trigger": "SCHEDULED",
        "candidates": rows,
        "summary": {"scanned": 2, "deep_analyzed": 2},
        "report_summary": {"production_buy_threshold": 73.0},
        "autonomous_decision_reduction": reduction,
    })


def test_historical_inventory_is_complete_and_no_longer_active_xfail_debt():
    payload = json.loads(MANIFEST.read_text(encoding="utf-8"))
    assert len(payload["tests"]) == 65
    assert {row["category"] for row in payload["tests"].values()} == {
        "historical_version_contract",
        "superseded_report_or_ui_contract",
    }
    conftest = (ROOT / "tests" / "conftest.py").read_text(encoding="utf-8")
    assert "pytest.mark.xfail" not in conftest
    assert "pytest_deselected" in conftest


def test_one_canonical_release_identity_replaces_old_literal_version_tests():
    assert APP_VERSION == "v19.22.0-rc16.31aq"
    tag = APP_VERSION.replace("-rc", "_RC")
    assert (ROOT / f"RELEASE_NOTES_{tag}.md").is_file()
    assert (ROOT / f"VALIDATION_REPORT_{tag}.md").is_file()


def test_fixed_report_contract_and_fresh_afternoon_are_explicit(monkeypatch):
    jobs, _ = mi.ensure_required_report_jobs([])
    assert [(job.job_id, job.schedules) for job in jobs] == [
        ("MI-REQUIRED-MORNING", ["08:00"]),
        ("MI-REQUIRED-AFTERNOON", ["14:00"]),
        ("MI-REQUIRED-EVENING", ["22:00"]),
    ]
    afternoon = jobs[1]
    calls = []
    monkeypatch.setattr(mi, "load_jobs", lambda: [afternoon])
    monkeypatch.setattr(mi, "_due_slot_info", lambda *args, **kwargs: {
        "due": True, "previous_planned_utc": "2026-08-27T12:00:00+00:00",
    })
    monkeypatch.setattr(mi, "upsert_job", lambda job: None)
    monkeypatch.setattr(mi, "_append_job_history", lambda row: None)
    monkeypatch.setattr(mi, "_audit", lambda *args, **kwargs: None)
    monkeypatch.setattr(mi, "scheduler_health_snapshot", lambda *args, **kwargs: {})
    monkeypatch.setattr(mi, "run_job", lambda job, **kwargs: calls.append(kwargs) or {"run_id": "RUN"})
    mi.run_due_jobs(authoritative_unattended=True)
    assert calls[0]["force_refresh"] is True


def test_moderate_recommendations_are_visible_but_never_trade_authorized():
    run = _canonical_run()
    moderate = [
        row for row in run["candidates"]
        if row.get("autonomy_outcome_code") == OUTCOME_MODERATE_BUY
    ]
    assert [row["ticker"] for row in moderate] == ["BMY", "WAWI.OL"]
    for row in moderate:
        allowed, reasons = production_buy_authorization(row)
        assert row["trade_authorized"] is False
        assert allowed is False
        assert reasons


def test_current_text_pdf_and_json_share_the_same_recommendations():
    run = _canonical_run()
    text = build_text_report(run).encode("utf-8")
    payload = json.dumps(run, ensure_ascii=False, default=str).encode("utf-8")
    decoded = text.decode("utf-8")
    assert "#1 BMY · Beslutning: Moderat kjøpsanbefaling" in decoded
    assert "#2 WAWI.OL · Beslutning: Moderat kjøpsanbefaling" in decoded
    for pdf in (build_main_pdf(run), build_technical_pdf(run)):
        audit = validate_artifacts(run=run, pdf=pdf, txt=text, json_bytes=payload)
        assert audit["ok"], audit["errors"]


def test_current_report_contract_is_norwegian_and_renderer_independent():
    run = _canonical_run()
    text = build_text_report(run)
    assert "Moderat kjøpsanbefaling" in text
    assert "beslutningsrapport" in text
    assert build_main_pdf(run).startswith(b"%PDF")
    assert build_technical_pdf(run).startswith(b"%PDF")
