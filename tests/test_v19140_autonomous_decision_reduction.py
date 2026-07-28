from __future__ import annotations

from copy import deepcopy

import investment_pipeline as ip
import market_intelligence as mi
from autonomous_decision_reduction import (
    OUTCOME_MANUAL,
    OUTCOME_REJECT,
    OUTCOME_WATCH,
    apply_decision_reduction,
    source_plan,
)
from market_universe import expand_market_scope


def _candidate(ticker: str, score: float, *, stage: str = "EVIDENCE_CONTROLLED", failure: bool = False):
    news_status = "PARTIAL_SOURCE_FAILURE" if failure else "NOT_SEARCHED"
    news_log = [{"source": "Primærkilde", "attempted": True, "status": "ERROR"}] if failure else []
    return {
        "ticker": ticker,
        "market": "USA",
        "investment_score": score,
        "risk_score": 30,
        "valid_for_decision": True,
        "evidence_valid_for_decision": False,
        "portfolio_action": "REVIEW",
        "analysis_stage": stage,
        "decision_readiness": {
            "news": news_status,
            "insider": "CHECKED_NO_EVENTS",
            "conflicts": 0,
        },
        "evidence_coverage": {
            "news": {"status": news_status, "search_log": news_log, "reason": "Kilden svarte ikke"},
            "insider": {"status": "CHECKED_NO_EVENTS", "search_log": []},
        },
        "raw": {},
    }


def test_market_groups_make_all_the_three_core_markets():
    assert expand_market_scope("Alle kjernemarkeder") == ["Norge", "Sverige", "USA"]
    assert expand_market_scope("Alle") == ["Norge", "Sverige", "USA"]
    assert expand_market_scope("Kjernemarkeder") == ["Norge", "Sverige", "USA"]
    assert expand_market_scope("Utvidet Norden") == ["Danmark", "Finland"]
    assert expand_market_scope("Brasil") == ["Brasil"]
    assert expand_market_scope("Alle markeder - full skanning") == ["USA", "Norge", "Sverige", "Finland", "Danmark", "Brasil"]
    assert mi.normalize_markets(["Alle"]) == ["Norge", "Sverige", "USA"]


def test_source_matrix_has_market_specific_primary_sources():
    assert source_plan("Norge", "news")[0] == "Oslo Børs NewsWeb"
    assert source_plan("USA", "financials")[0] == "SEC 10-Q/10-K"
    assert source_plan("Brasil", "news")[0] == "CVM"
    assert source_plan("Finland", "insider")[0] == "Finanssivalvonta"


def test_not_searched_is_automatic_watch_not_manual_work():
    rows, summary = apply_decision_reduction([_candidate("AAA", 77, stage="EXTENDED_ANALYSIS")])
    assert rows[0]["autonomy_outcome_code"] == OUTCOME_WATCH
    assert rows[0]["manual_tasks"] == []
    assert summary["manual_task_count"] == 0


def test_weak_candidate_is_rejected_without_expensive_manual_work():
    rows, summary = apply_decision_reduction([_candidate("LOW", 60, failure=True)])
    assert rows[0]["autonomy_outcome_code"] == OUTCOME_REJECT
    assert rows[0]["manual_tasks"] == []
    assert summary["automatic_rejected"] == 1


def test_manual_work_is_concrete_and_globally_limited_to_two_tasks():
    candidates = [_candidate(f"T{i}", 77 - i / 10, failure=True) for i in range(4)]
    rows, summary = apply_decision_reduction(candidates, max_manual_tasks=2)
    assert summary["manual_task_count"] == 2
    assert sum(row["autonomy_outcome_code"] == OUTCOME_MANUAL for row in rows) <= 2
    required = {"title", "why", "program_attempts", "failure_reason", "suggested_source", "decision_impact"}
    for task in summary["manual_tasks"]:
        assert required <= set(task)
        assert all(str(task[key]).strip() for key in required)


def test_priority_top3_is_restored_without_being_a_buy_list():
    candidates = [
        _candidate("WATCH", 79, stage="EXTENDED_ANALYSIS"),
        _candidate("MANUAL", 78, failure=True),
        _candidate("WATCH2", 77, stage="EXTENDED_ANALYSIS"),
        _candidate("REJECT", 50, failure=True),
    ]
    rows, summary = apply_decision_reduction(candidates)
    priority = summary["priority_top3"]
    assert [row["priority_rank"] for row in priority] == [1, 2, 3]
    assert all(row["autonomy_outcome_code"] != OUTCOME_REJECT for row in priority)
    assert {row["ticker"] for row in priority} == {"WATCH", "MANUAL", "WATCH2"}


def test_pipeline_only_calls_expensive_sources_for_stage3_budget(monkeypatch):
    rows = [
        {
            "ticker": f"T{i}", "market": "USA", "scanner_score": 90 - i,
            "momentum_score": 80 - i, "liquidity_score": 85, "data_quality": 95,
            "risk_score": 20 + i, "price": 100 + i, "volume": 1_000_000,
        }
        for i in range(8)
    ]
    monkeypatch.setattr(ip, "_prepare_candidate_rows", lambda rows, cfg, progress_callback=None, force_refresh=False: deepcopy(rows))
    monkeypatch.setattr(ip, "_read_json", lambda *args, **kwargs: {})
    monkeypatch.setattr(ip, "_write_json", lambda *args, **kwargs: None)

    import insider_intelligence
    import news_intelligence

    calls = {"insider": 0, "news": 0}

    def insider_enrich(items, **kwargs):
        calls["insider"] += len(items)
        return [{**item, "insider_intelligence": {"coverage": "CHECKED_NO_EVENTS"}} for item in items]

    def news_enrich(items, **kwargs):
        calls["news"] += len(items)
        return [{**item, "news_intelligence": {"coverage": "CHECKED_NO_EVENTS"}} for item in items]

    monkeypatch.setattr(insider_intelligence, "enrich_rows", insider_enrich)
    monkeypatch.setattr(news_intelligence, "enrich_rows", news_enrich)

    cfg = ip.PipelineConfig(
        market_scope="USA", scan_limit=8, deep_analysis_count=5, proposal_count=2,
        use_research=False, use_backtest=False, use_portfolio_fit=False,
        use_learning_advisor=False, use_insider_intelligence=True, use_news_intelligence=True,
    )
    result = ip.run_pipeline(rows, cfg)
    assert result["analysis_stages"]["stage1"]["input"] == 8
    assert result["analysis_stages"]["stage2"]["input"] == 5
    assert result["analysis_stages"]["stage3"]["completed"] == 2
    assert calls == {"insider": 2, "news": 2}
    assert len(result["candidates"]) == 5
    assert sum(row["analysis_stage"] == "EVIDENCE_CONTROLLED" for row in result["candidates"]) == 2
    not_deep = [row for row in result["candidates"] if row["analysis_stage"] != "EVIDENCE_CONTROLLED"]
    assert all((row["raw"].get("news_intelligence") or {}).get("coverage") == "NOT_SEARCHED" for row in not_deep)


def test_total_evidence_budget_can_allocate_zero_to_a_market():
    assert [mi._allocated_market_budget(5, index, 6, minimum=0) for index in range(1, 7)] == [1, 1, 1, 1, 1, 0]
    assert ip.PipelineConfig(deep_analysis_count=3, proposal_count=0).normalized().proposal_count == 0


def test_priority_top3_is_filled_with_clearly_rejected_fallbacks():
    candidates = [_candidate("WATCH", 77, stage="EXTENDED_ANALYSIS"), _candidate("R1", 60), _candidate("R2", 59)]
    rows, summary = apply_decision_reduction(candidates)
    assert len(summary["priority_top3"]) == 3
    assert summary["priority_top3"][0]["ticker"] == "WATCH"
    assert all(row["autonomy_outcome_code"] == OUTCOME_REJECT for row in summary["priority_top3"][1:])


def test_report_document_prefers_autonomy_outcome_over_legacy_review():
    from report_contracts import _candidate_decisions

    row = _candidate("WATCH", 77, stage="EXTENDED_ANALYSIS")
    row["autonomy_outcome_code"] = OUTCOME_WATCH
    row["autonomy_outcome_label"] = "Overvåkes automatisk"
    contract = {
        "ticker": "WATCH",
        "action": OUTCOME_WATCH,
        "action_label": "Overvåkes automatisk",
        "confidence": {},
    }
    rendered = _candidate_decisions([row], [contract])[0]
    assert rendered["action"] == OUTCOME_WATCH
    assert rendered["status"] == "Overvåkes automatisk"
