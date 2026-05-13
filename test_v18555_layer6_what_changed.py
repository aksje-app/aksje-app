from pathlib import Path

from app_version import get_app_version
from fund_etf_analyzer import (
    attach_and_store_what_changed,
    build_what_changed_profile,
    load_latest_fund_analysis_snapshot,
)


def _result(a_score=70, b_score=65, order=("AAA", "BBB")):
    rows = {
        "AAA": {
            "symbol": "AAA",
            "name": "Alpha Fund",
            "fund_intelligence_score": a_score,
            "decision_quality": a_score,
            "base_score": a_score,
            "data_quality": 90,
            "fund_type": "ETF",
            "decision": "Kandidat",
            "grade": "Høy",
            "reasons_caution": ["kostnad må overvåkes"],
            "insider_holdings_profile": {"direction": "Nøytral", "insider_score": 50, "covered_top_holdings_weight_pct": 25},
        },
        "BBB": {
            "symbol": "BBB",
            "name": "Beta Fund",
            "fund_intelligence_score": b_score,
            "decision_quality": b_score,
            "base_score": b_score,
            "data_quality": 88,
            "fund_type": "ETF",
            "decision": "Kandidat",
            "grade": "Middels",
            "reasons_caution": ["lavere datakvalitet"],
            "insider_holdings_profile": {"direction": "Positiv", "insider_score": 74, "covered_top_holdings_weight_pct": 40},
        },
    }
    return {
        "version": get_app_version(),
        "fund_type": "ETF",
        "objective": "Balansert",
        "test_mode": "Normal",
        "benchmark_symbol": "SPY",
        "symbols": ["AAA", "BBB"],
        "summary": {"analyzed": 2},
        "ranked": [rows[s] for s in order],
    }


def test_v18555_version():
    assert get_app_version() == "v18.5.70"


def test_first_run_stores_snapshot_and_reports_no_previous(tmp_path: Path):
    result = attach_and_store_what_changed(_result(), snapshot_dir=tmp_path)
    assert result["what_changed_profile"]["has_previous"] is False
    assert result["snapshot_storage"]["stored"] is True
    assert list(tmp_path.glob("fund_analysis__*.json"))


def test_second_run_detects_rank_and_score_changes(tmp_path: Path):
    first = attach_and_store_what_changed(_result(a_score=80, b_score=60, order=("AAA", "BBB")), snapshot_dir=tmp_path)
    context = first["snapshot_storage"]["snapshot"]["context_key"]
    assert load_latest_fund_analysis_snapshot(context, snapshot_dir=tmp_path)

    second = attach_and_store_what_changed(_result(a_score=62, b_score=88, order=("BBB", "AAA")), snapshot_dir=tmp_path)
    prof = second["what_changed_profile"]
    assert prof["has_previous"] is True
    assert any(m["symbol"] == "BBB" and m["direction"] == "opp" for m in prof["rank_movers"])
    assert any(m["symbol"] == "AAA" and m["score_delta"] < 0 for m in prof["score_movers"])


def test_build_what_changed_without_previous_is_safe():
    prof = build_what_changed_profile(_result(), None)
    assert prof["model"] == "What Changed Intelligence"
    assert prof["new_funds"] == ["AAA", "BBB"]
