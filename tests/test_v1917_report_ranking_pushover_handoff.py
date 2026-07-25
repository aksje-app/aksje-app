from __future__ import annotations

from market_intelligence import (
    build_autonomy_candidate_handoff,
    build_ranking_explanation,
    _notification_status_explanation,
)
from norwegian_report_language import label_for, translate_report_text
from autonomi_core.runtime.orchestrator import execute_market_mission


def _candidate(ticker: str, score: float, news: float, action: str = "REVIEW") -> dict:
    return {
        "ticker": ticker,
        "investment_score": score,
        "portfolio_action": action,
        "valid_for_decision": True,
        "data_quality": 100,
        "risk_score": 20,
        "raw": {"news_score": news},
        "decision_readiness": {"allowed_action": action, "news": "VERIFIED_FACTS_FOUND", "insider": "CHECKED_NO_EVENTS"},
        "data_contract": {"validity": "VALID"},
    }


def test_pushover_explanation_never_says_unknown_not_searched_without_reason():
    assert _notification_status_explanation({}) == "Pushover ikke forsøkt: Ingen varslingsbeslutning registrert"
    assert "Test uten varsling" in _notification_status_explanation({"attempted": False, "detail": "Test uten varsling: Pushover ble ikke sendt"})
    assert _notification_status_explanation({"sent": True}) == "Pushover sendt"


def test_ranking_explains_news_leader_outside_top3():
    run = {
        "candidates": [_candidate("STB.OL", 65, 99), _candidate("ATO", 74, 50), _candidate("AWK", 73, 40)],
        "decision_ready_top3": [_candidate("ATO", 74, 50), _candidate("AWK", 73, 40)],
        "raw_top3": [_candidate("STB.OL", 65, 99), _candidate("ATO", 74, 50), _candidate("AWK", 73, 40)],
        "portfolio_decisions": {"production_threshold": 73},
    }
    explanation = build_ranking_explanation(run)
    assert explanation["news_leader"]["ticker"] == "STB.OL"
    assert "STB.OL hadde sterkest nyhetsscore" in explanation["note"]
    assert "score" in explanation["note"]


def test_autonomy_handoff_detects_report_candidates_but_zero_received():
    run = {"candidates": [_candidate("ATO", 74, 50)], "proposals": [], "decision_ready_top3": []}
    chain = {"stages": [{"name": "MARKET_SCAN", "status": "OK", "detail": {"candidates": 0}}]}
    handoff = build_autonomy_candidate_handoff(run, chain)
    assert handoff["mismatch"] is True
    assert handoff["report_candidates"] == 1
    assert handoff["sent_to_autonomy"] == 0


def test_review_candidates_are_forwarded_to_autonomy_runtime(monkeypatch):
    captured = {}
    def fake_run_post_scan_chain(governed_run, **kwargs):
        captured.update(governed_run)
        return {"status": "OK", "stages": [{"name": "MARKET_SCAN", "status": "OK", "detail": {"candidates": len(governed_run.get("candidates") or [])}}]}
    import autonomous_orchestrator
    monkeypatch.setattr(autonomous_orchestrator, "run_post_scan_chain", fake_run_post_scan_chain)
    result = execute_market_mission({"run_id": "T", "candidates": [_candidate("ATO", 74, 50, "REVIEW")]}, run_autonomous=True, run_learning=False, require_active_portfolio=False)
    assert len(captured.get("candidates") or []) == 1
    assert captured["autonomy_handoff_input"]["review_candidates_forwarded"] == 1
    assert result["autonomy_core"]["handoff_input"]["forwarded_candidates"] == 1


def test_norwegian_language_for_new_statuses():
    assert label_for("THEORETICAL_ONLY") == "Kun teoretisk"
    assert "Utfordrer" in translate_report_text("CHALLENGER")
