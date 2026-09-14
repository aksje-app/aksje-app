from __future__ import annotations

from pathlib import Path

import evidence_integrity
import market_intelligence as mi
from autonomi_core.runtime.full_execution import build_full_execution_receipt, reconcile_portfolio_assessment
from production_coverage_contract import build_production_coverage_contract
from report_portfolio_intelligence import ensure_portfolio_evidence
from short_intelligence import build_short_report


def _area(status: str, *, attempted: bool, reason_code: str, results: int = 0) -> dict:
    return {
        "search_log": [{
            "source": "test source", "status": status, "attempted": attempted,
            "reason_code": reason_code, "results": results,
        }]
    }


def _candidate(ticker: str = "ABC", *, news: dict | None = None, insider: dict | None = None) -> dict:
    return {
        "ticker": ticker,
        "market": "USA",
        "investment_score": 80.0,
        "valid_for_decision": True,
        "evidence_data_ready": True,
        "final_decision_ready": False,
        "raw": {
            "last_price": 100.0,
            "news_intelligence": news if news is not None else _area("SUCCESS_NO_RESULTS", attempted=True, reason_code="NO_RELEVANT_RESULTS"),
            "insider_intelligence": insider if insider is not None else _area("SUCCESS_NO_RESULTS", attempted=True, reason_code="NO_RELEVANT_RESULTS"),
            "short_data": {"coverage_status": "NO_REPORTED_DATA"},
        },
    }


def test_one_canonical_coverage_denominator_for_all_four_areas():
    rows = [_candidate("AAA"), _candidate("BBB")]
    contract = build_production_coverage_contract(rows)
    assert contract["candidate_total"] == 2
    assert contract["unique_ticker_total"] == 2
    assert contract["structurally_complete"] is True
    assert set(contract["areas"]) == {"market", "news", "insider", "short"}
    assert {area["required"] for area in contract["areas"].values()} == {2}
    assert {area["completed"] for area in contract["areas"].values()} == {2}


def test_short_checked_without_public_position_is_checked_not_unknown():
    report = build_short_report([_candidate("AAA"), _candidate("BBB")])
    assert report["candidate_count"] == 2
    assert report["checked_count"] == 2
    assert report["no_public_position_count"] == 2
    assert report["not_searched_count"] == 0
    assert report["unknown_count"] == 0


def test_documented_rank_policy_is_terminal_but_unknown_reason_is_structural_gap():
    limited = _candidate(
        "LIMITED",
        news=_area("NOT_SEARCHED", attempted=False, reason_code="RANK_LIMIT"),
    )
    limited_contract = build_production_coverage_contract([limited])
    assert limited_contract["areas"]["news"]["not_searched"] == 1
    assert limited_contract["areas"]["news"]["unknown_reason"] == 0
    assert limited_contract["structurally_complete"] is True

    unknown = _candidate("UNKNOWN", news={})
    unknown_contract = build_production_coverage_contract([unknown])
    assert unknown_contract["areas"]["news"]["unknown_reason"] == 1
    assert unknown_contract["structurally_complete"] is False


def test_final_status_distinguishes_source_limitations_from_technical_incompleteness():
    limited = _candidate(
        "LIMITED",
        news=_area("NOT_SEARCHED", attempted=False, reason_code="RANK_LIMIT"),
    )
    final_run = {
        "run_id": "RUN-FINAL", "candidates": [limited], "raw_top3": [limited],
        "production_coverage_contract": build_production_coverage_contract([limited]),
        "report_integrity": {"ok": True},
    }
    evidence_integrity.finalize_run_integrity(final_run)
    assert final_run["report_status"]["state"] == "FINAL"
    assert "KILDEBEGRENSNINGER" in final_run["report_status"]["label"]

    unknown = _candidate("UNKNOWN", news={})
    provisional = {
        "run_id": "RUN-PROVISIONAL", "candidates": [unknown], "raw_top3": [unknown],
        "production_coverage_contract": build_production_coverage_contract([unknown]),
        "report_integrity": {"ok": True},
    }
    evidence_integrity.finalize_run_integrity(provisional)
    assert provisional["report_status"]["state"] == "PROVISIONAL"
    assert provisional["report_status"]["revalidation_required"] is True


def test_portfolio_only_position_gets_explicit_complete_coverage(monkeypatch):
    def short_rows(rows, force_refresh=False):
        return [{**row, "short_data": {"coverage_status": "NO_REPORTED_DATA"}} for row in rows]

    def insider_rows(rows, force_refresh=False):
        return [{
            **row,
            "insider_intelligence": _area(
                "SUCCESS_NO_RESULTS", attempted=True, reason_code="NO_RELEVANT_RESULTS"
            ),
        } for row in rows]

    monkeypatch.setattr("short_data_sources.enrich_rows", short_rows)
    monkeypatch.setattr("insider_intelligence.enrich_rows", insider_rows)
    positions = {"positions": {"VBBR3.SA": {
        "ticker": "VBBR3.SA", "last_price": 18.4,
        "raw": {"insider_intelligence": {}},
    }}}
    rows = ensure_portfolio_evidence(positions, [_candidate("AAA")])
    appended = next(row for row in rows if row["ticker"] == "VBBR3.SA")
    assert appended["market"] == "Brasil"
    assert appended["coverage_role"] == "PORTFOLIO_ONLY_EXISTING_POSITION"
    contract = build_production_coverage_contract(rows)
    ledger = next(row for row in contract["ledger"] if row["ticker"] == "VBBR3.SA")
    assert ledger["areas"]["market"]["status"] == "SEARCHED_RESULTS_FOUND"
    assert ledger["areas"]["news"]["status"] == "NOT_APPLICABLE"
    assert ledger["areas"]["insider"]["status"] == "SEARCHED_NO_RESULTS"
    assert ledger["areas"]["short"]["status"] == "SEARCHED_NO_RESULTS"
    assert contract["structurally_complete"] is True


def test_portfolio_assessment_closes_every_candidate_even_with_zero_buys():
    run = {
        "candidates": [
            {"ticker": "AAA", "portfolio_action": "HOLD"},
            {"ticker": "BBB", "portfolio_action": "SKIP"},
        ],
        "portfolio_decisions": {"decisions": [{"ticker": "AAA", "action": "HOLD"}]},
    }
    contract = reconcile_portfolio_assessment(run)
    assert contract == {
        "candidate_count": 2, "decision_count": 2, "all_assessed": True,
        "reconciled_after_autonomy": True,
    }
    assert run["portfolio_decisions"]["actions"]["BUY"] == 0
    assert all(row["portfolio_assessed"] for row in run["portfolio_decisions"]["decisions"])


def test_mobile_report_actions_are_above_iframe_and_keep_return_path():
    source = Path("public_report_ui.py").read_text(encoding="utf-8")
    assert source.index("Last ned / del PDF") < source.index("<iframe")
    assert source.index("Tilbake til programmet") < source.index("<iframe")
    assert "render_mobile_file_delivery(" in source
    delivery = Path("mobile_file_delivery.py").read_text(encoding="utf-8")
    assert "st.download_button(" in delivery
    assert "st.code(" in delivery
    assert 'st.link_button("← Tilbake til programmet", "/"' in source


def test_required_report_schedule_contract_remains_08_14_22():
    jobs, _ = mi.ensure_required_report_jobs([])
    required = {job.job_id: job.schedules for job in jobs if job.job_id.startswith("MI-REQUIRED-")}
    assert required == {
        "MI-REQUIRED-MORNING": ["08:00"],
        "MI-REQUIRED-AFTERNOON": ["14:00"],
        "MI-REQUIRED-EVENING": ["22:00"],
    }


def test_pushover_uses_canonical_coverage_denominator():
    source = Path("market_intelligence.py").read_text(encoding="utf-8")
    assert 'report_summary_notice.get("coverage_candidate_total")' in source
    assert 'f"Analysert: {candidate_total_notice}"' in source
    assert 'evidens {evidence_ready_notice}/{candidate_total_notice}' in source


def test_pdf_uses_canonical_coverage_denominator_not_stale_quality_population():
    source = Path("market_intelligence.py").read_text(encoding="utf-8")
    assert 'report_summary_pdf.get("coverage_candidate_total")' in source
    assert 'coverage_contract_pdf.get("candidate_total")' in source
    assert 'combined_quality.get("evaluated") or len(run.get("candidates")' not in source
