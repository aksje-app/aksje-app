import json
from pathlib import Path

from evidence_search_status import (
    NOT_SEARCHED_BUDGET,
    NOT_SEARCHED_POLICY,
    SEARCHED_NO_RESULTS,
    SEARCHED_RESULTS_FOUND,
    SEARCH_FAILED,
    build_run_search_summary,
    normalize_evidence_payload,
    normalize_search_attempt,
)
from investment_pipeline import _mark_intelligence_not_searched
from market_intelligence import apply_evidence_coverage_policy
from tools.audit_evidence_search_v19220_rc10 import audit


def test_search_attempts_are_normalized_without_replacing_legacy_status():
    found = normalize_search_attempt({
        "source": "A", "attempted": True, "status": "SUCCESS_WITH_RESULTS", "results": 2,
    })
    none = normalize_search_attempt({
        "source": "B", "attempted": True, "status": "SUCCESS_NO_RESULTS", "results": 0,
    })
    failed = normalize_search_attempt({
        "source": "C", "attempted": True, "status": "RATE_LIMITED", "error": "HTTP 429",
    })
    budget = normalize_search_attempt({
        "source": "D", "attempted": False, "status": "SKIPPED_BUDGET_POLICY",
        "error": "Døgnbudsjett bevart",
    })
    assert found["status"] == "SUCCESS_WITH_RESULTS"
    assert found["search_status"] == SEARCHED_RESULTS_FOUND
    assert none["search_status"] == SEARCHED_NO_RESULTS
    assert failed["search_status"] == SEARCH_FAILED
    assert failed["reason_code"] == "RATE_LIMITED"
    assert budget["search_status"] == NOT_SEARCHED_BUDGET
    assert budget["reason_code"] == "BUDGET_POLICY"


def test_reasoned_pipeline_skip_has_no_plain_unknown_not_searched():
    row = {}
    _mark_intelligence_not_searched(
        row,
        "news",
        "Ikke prioritert til full evidenskontroll etter rangering.",
        reason_code="RANK_LIMIT",
    )
    payload = row["news_intelligence"]
    assert payload["coverage"] == "NOT_SEARCHED"  # Legacy gate semantics retained.
    assert payload["search_status"] == NOT_SEARCHED_POLICY
    assert payload["search_unknown_reason_count"] == 0
    assert payload["source_budget"]["planned"] == 1
    assert payload["source_budget"]["attempted"] == 0
    assert payload["search_log"][0]["reason_code"] == "RANK_LIMIT"


def test_payload_budget_is_derived_from_actual_log():
    payload = normalize_evidence_payload({
        "search_log": [
            {"source": "A", "attempted": True, "status": "SUCCESS_WITH_RESULTS", "results": 3},
            {"source": "B", "attempted": False, "status": "SKIPPED_BUDGET_POLICY", "results": 0},
        ],
    }, area="news")
    assert payload["search_status"] == SEARCHED_RESULTS_FOUND
    assert payload["source_budget"] == {
        "planned": 2,
        "attempted": 1,
        "successful": 1,
        "with_facts": 1,
        "no_events": 0,
        "failed": 0,
        "not_searched": 1,
        "not_applicable": 0,
        "unknown_reason": 0,
        "rate_limited": 0,
        "daily_quota_exceeded": 0,
        "not_configured": 0,
        "errors": 0,
    }


def test_evidence_policy_adds_search_contract_without_changing_investment_score():
    candidate = {
        "ticker": "TEST.OL",
        "investment_score": 78.5,
        "confidence_score": 90.0,
        "status": "ANBEFALT FOR VURDERING",
        "portfolio_action": "BUY",
        "raw": {
            "news_intelligence": {
                "coverage": "CHECKED_NO_EVENTS",
                "search_log": [{"source": "News", "attempted": True, "status": "SUCCESS_NO_RESULTS"}],
                "events": [],
            },
            "insider_intelligence": {
                "coverage": "CHECKED_NO_EVENTS",
                "search_log": [{"source": "Insider", "attempted": True, "status": "SUCCESS_NO_RESULTS"}],
                "evidence": [],
            },
        },
    }
    before = candidate["investment_score"]
    summary = apply_evidence_coverage_policy([candidate])
    assert candidate["investment_score"] == before
    assert candidate["evidence_valid_for_decision"] is True
    assert candidate["raw"]["news_intelligence"]["search_status"] == SEARCHED_NO_RESULTS
    assert candidate["raw"]["insider_intelligence"]["search_status"] == SEARCHED_NO_RESULTS
    assert summary["search_unknown_reason_count"] == 0


def test_run_summary_counts_areas_not_nested_status_fields():
    candidate = {
        "ticker": "TEST.OL",
        "market": "Norge",
        "raw": {
            "news_intelligence": {
                "search_log": [{"source": "A", "attempted": True, "status": "SUCCESS_NO_RESULTS"}],
            },
            "insider_intelligence": {
                "coverage": "NOT_SEARCHED",
                "reason": "Ikke prioritert etter rangering",
                "search_log": [],
            },
        },
    }
    summary = build_run_search_summary([candidate])
    assert summary["candidate_count"] == 1
    assert summary["area_count"] == 2
    assert summary["status_counts"][SEARCHED_NO_RESULTS] == 1
    assert summary["status_counts"][NOT_SEARCHED_POLICY] == 1
    assert summary["reason_counts"]["RANK_LIMIT"] == 1
    assert summary["unknown_reason_count"] == 0


def test_audit_counts_unique_sources_and_loads_historical_trades(tmp_path: Path):
    report = {
        "run_id": "MI-TEST",
        "app_version": "v19.22.0-rc10",
        "markets": ["Norge"],
        "candidates": [{
            "ticker": "TEST.OL",
            "market": "Norge",
            "investment_score": 70,
            "evidence_valid_for_decision": False,
            "raw": {
                "news_intelligence": {
                    "coverage": "NOT_SEARCHED",
                    "reason": "Ikke prioritert etter rangering",
                    "search_log": [],
                    "source_budget": {"planned": 1, "attempted": 0, "successful": 0, "with_facts": 0, "errors": 0},
                },
                "insider_intelligence": {
                    "coverage": "CHECKED_NO_EVENTS",
                    "search_log": [{"source": "Official", "attempted": True, "status": "SUCCESS_NO_RESULTS"}],
                    "source_budget": {"planned": 1, "attempted": 1, "successful": 1, "with_facts": 0, "no_events": 1, "errors": 0},
                },
            },
        }],
    }
    report_path = tmp_path / "report.json"
    report_path.write_text(json.dumps(report), encoding="utf-8")
    trades_path = tmp_path / "trades.json"
    trades_path.write_text(json.dumps([{
        "action": "BUY", "ticker": "OLD", "run_id": "MI-OLD",
        "timestamp": "2026-07-20T10:00:00+00:00", "reason": "Score 75.5",
        "mode": "THEORETICAL_ONLY", "strategy_role": "AUTONOMY_MAIN",
    }]), encoding="utf-8")

    result = audit([report_path], trades_path)
    assert result["reports_analyzed"] == 1
    assert result["candidates_analyzed"] == 1
    assert result["unique_source_area_records"] == 2
    assert result["unique_not_searched_records"] == 1
    assert result["unknown_reason_records"] == 0
    assert result["budget_issue_count"] == 0
    assert result["historical_autonomy_reference"]["buy_count"] == 1
    assert result["historical_autonomy_reference"]["buy_score_min"] == 75.5
    assert all(result["acceptance"].values())


def test_operations_ui_exposes_evidence_search_diagnostics():
    source = Path("market_intelligence.py").read_text(encoding="utf-8")
    assert 'st.markdown("#### Evidenssøksdiagnostikk")' in source
    assert 'metric("Planlagte kildesøk"' in source
    assert 'metric("Søkefeil"' in source
    assert 'Kandidatdetaljer for evidenssøk' in source


def test_canonical_report_rewrites_legacy_source_budget_from_search_log():
    from report_integrity import canonical_report_view

    run = {
        "run_id": "MI-LEGACY",
        "created_at": "2026-08-04T20:00:00+02:00",
        "candidates": [{
            "ticker": "TEST.OL",
            "market": "Norge",
            "investment_score": 70.0,
            "raw": {
                "news_intelligence": {
                    "coverage": "NOT_SEARCHED",
                    "reason": "Ikke prioritert etter rangering",
                    "search_log": [],
                    "source_budget": {"planned": 0, "attempted": 0},
                },
                "insider_intelligence": {
                    "coverage": "CHECKED_NO_EVENTS",
                    "search_log": [{"source": "Official", "attempted": True, "status": "SUCCESS_NO_RESULTS"}],
                    "source_budget": {"planned": 99, "attempted": 0},
                },
            },
        }],
    }
    normalized = canonical_report_view(run)
    candidate = normalized["candidates"][0]
    news = candidate["raw"]["news_intelligence"]
    insider = candidate["raw"]["insider_intelligence"]
    assert news["source_budget"]["planned"] == 1
    assert news["source_budget"]["not_searched"] == 1
    assert insider["source_budget"]["planned"] == 1
    assert insider["source_budget"]["successful"] == 1
    assert normalized["evidence_search_summary"]["unknown_reason_count"] == 0
