from autonomous_decision_reduction import (
    OUTCOME_BUY,
    OUTCOME_MODERATE_BUY,
    OUTCOME_REJECT,
    apply_decision_reduction,
    classify_candidate,
)
from autonomous_portfolio import production_buy_authorization
from report_contracts import build_report_document, section_payload
from report_export_audit import canonical_public_run, validate_artifacts
from market_intelligence import build_main_pdf, build_technical_pdf, build_text_report
from report_replay_export import _candidate_scores, classify_replay_case
import market_intelligence as mi
import json


def candidate(ticker="TEST", market="USA", score=70.0, risk=30.0, **extra):
    row = {
        "ticker": ticker,
        "market": market,
        "investment_score": score,
        "risk_score": risk,
        "valid_for_decision": True,
        "evidence_valid_for_decision": True,
        "mission_eligible": True,
        "analysis_stage": "EVIDENCE_CONTROLLED",
        "portfolio_action": "REVIEW",
        "portfolio_decision": {"existing_position": False, "blockers": ["Maks antall posisjoner"]},
        "decision_readiness": {"news": "VERIFIED_FACTS_FOUND", "insider": "CHECKED_NO_EVENTS", "conflicts": 0},
        "raw": {},
    }
    row.update(extra)
    return row


def test_moderate_recommendations_are_produced_in_all_three_core_markets():
    rows, summary = apply_decision_reduction([
        candidate("NORD.OL", "Norge", 70.5),
        candidate("SVEA.ST", "Sverige", 69.5),
        candidate("USCO", "USA", 71.5),
    ], threshold=73.0, near_threshold_gap=6.0, maximum_risk=65.0)
    assert {row["market"] for row in rows if row["autonomy_outcome_code"] == OUTCOME_MODERATE_BUY} == {"Norge", "Sverige", "USA"}
    assert summary["moderate_buy_recommendations"] == 3
    assert summary["analytical_buy_recommendations"] == 3


def test_moderate_never_authorizes_a_trade():
    row = classify_candidate(candidate(), threshold=73.0, maximum_risk=65.0)
    assert row["autonomy_outcome_code"] == OUTCOME_MODERATE_BUY
    assert row["trade_authorized"] is False
    allowed, reasons = production_buy_authorization(row)
    assert not allowed
    assert reasons


def test_strict_buy_contract_is_unchanged():
    row = classify_candidate(candidate(score=80, portfolio_action="BUY"), threshold=73.0, maximum_risk=65.0)
    assert row["autonomy_outcome_code"] == OUTCOME_BUY


def test_invalid_high_risk_existing_and_source_error_are_not_moderate():
    cases = [
        candidate(valid_for_decision=False),
        candidate(risk=70),
        candidate(portfolio_decision={"existing_position": True}),
        candidate(decision_readiness={"news": "SOURCE_ERROR", "insider": "CHECKED_NO_EVENTS", "conflicts": 0}),
        candidate(raw={"insider_signal": "STERKT NEGATIV"}),
        candidate(technical_entry_wait=True),
    ]
    assert all(classify_candidate(row, threshold=73.0, maximum_risk=65.0)["autonomy_outcome_code"] != OUTCOME_MODERATE_BUY for row in cases)


def test_far_below_threshold_is_rejected():
    row = classify_candidate(candidate(score=66.9), threshold=73.0, near_threshold_gap=6.0)
    assert row["autonomy_outcome_code"] == OUTCOME_REJECT


def test_moderate_recommendations_pass_real_cross_channel_export_gate():
    rows, reduction = apply_decision_reduction([
        {**candidate("BMY", "USA", 71.39), "rank": 17},
        {**candidate("WAWI.OL", "Norge", 70.93), "rank": 19},
    ], threshold=73.0, near_threshold_gap=6.0, maximum_risk=65.0)
    run = {
        "run_id": "MI-RC16-31AQ-CROSS-CHANNEL",
        "created_at": "2026-08-27T14:00:00+00:00",
        "timezone_name": "Europe/Oslo",
        "job_id": "MI-REQUIRED-AFTERNOON",
        "job_name": "Obligatorisk ettermiddagsrapport",
        "trigger": "SCHEDULED",
        "candidates": rows,
        "summary": {"scanned": 2, "deep_analyzed": 2},
        "report_summary": {"production_buy_threshold": 73.0},
        "autonomous_decision_reduction": reduction,
    }
    canonical = canonical_public_run(run)
    txt = build_text_report(canonical).encode("utf-8")
    payload = json.dumps(canonical, ensure_ascii=False, default=str).encode("utf-8")
    assert "#1 BMY · Beslutning: Moderat kjøpsanbefaling" in txt.decode("utf-8")
    assert "#2 WAWI.OL · Beslutning: Moderat kjøpsanbefaling" in txt.decode("utf-8")
    for pdf in (build_main_pdf(canonical), build_technical_pdf(canonical)):
        audit = validate_artifacts(run=canonical, pdf=pdf, txt=txt, json_bytes=payload)
        assert audit["ok"], audit["errors"]


def test_compact_pdf_does_not_require_technical_learning_fill_appendix():
    run = {
        "run_id": "MI-RC16-31AQ-COMPACT",
        "created_at": "2026-08-27T08:00:00+00:00",
        "timezone_name": "Europe/Oslo",
        "job_id": "MI-REQUIRED-MORNING",
        "job_name": "Obligatorisk morgenrapport",
        "trigger": "SCHEDULED",
        "candidates": [],
        "summary": {},
        "learning_portfolio_summary": {
            "learning_fills": [{"ticker": "SCHW", "side": "BUY", "quantity": 1, "price": 112.53}],
        },
    }
    canonical = canonical_public_run(run)
    txt = build_text_report(canonical).encode("utf-8")
    payload = json.dumps(canonical, ensure_ascii=False, default=str).encode("utf-8")
    audit = validate_artifacts(
        run=canonical, pdf=build_main_pdf(canonical), txt=txt, json_bytes=payload,
    )
    assert audit["ok"], audit["errors"]


def test_portfolio_only_rows_are_not_false_missing_scores():
    run = {"candidates": [
        {"ticker": "BMY", "investment_score": 71.39, "status": "Moderat kjøpsanbefaling"},
        {"ticker": "FRT", "investment_score": None, "coverage_role": "PORTFOLIO_ONLY_EXISTING_POSITION", "status": "Automatisk avvist"},
    ]}
    scores = _candidate_scores(run)
    assert scores["scored_count"] == 1
    assert scores["not_applicable_count"] == 1
    assert scores["missing_count"] == 0
    _level, missing = classify_replay_case(run)
    assert "candidate_scores" not in missing


def test_scheduled_afternoon_run_forces_fresh_data(monkeypatch):
    jobs, _ = mi.ensure_required_report_jobs([])
    afternoon = next(job for job in jobs if job.job_id == "MI-REQUIRED-AFTERNOON")
    calls = []
    monkeypatch.setattr(mi, "load_jobs", lambda: [afternoon])
    monkeypatch.setattr(mi, "_due_slot_info", lambda *args, **kwargs: {
        "due": True, "previous_planned_utc": "2026-08-27T12:00:00+00:00",
    })
    monkeypatch.setattr(mi, "upsert_job", lambda job: None)
    monkeypatch.setattr(mi, "_append_job_history", lambda row: None)
    monkeypatch.setattr(mi, "_audit", lambda *args, **kwargs: None)
    monkeypatch.setattr(mi, "scheduler_health_snapshot", lambda *args, **kwargs: {})
    monkeypatch.setattr(mi, "run_job", lambda job, **kwargs: calls.append(kwargs) or {"run_id": "RUN-AFTERNOON"})
    mi.run_due_jobs(authoritative_unattended=True)
    assert calls[0]["force_refresh"] is True
