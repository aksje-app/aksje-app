from app_version import APP_VERSION
from investment_pipeline import PipelineConfig
from universe_coverage import (
    build_buy_gate_audit,
    build_selection_trace,
    build_universe_contract,
    configured_universe_tickers,
    select_sector_balanced_rows,
)


def test_release_version_and_full_universe_configuration():
    assert APP_VERSION == "v19.22.0-rc16.31g"
    cfg = PipelineConfig(market_scope="Norge", scan_limit=25, full_universe_scan=True).normalized()
    assert cfg.scan_limit == 500
    assert cfg.full_universe_scan is True


def test_packaged_universe_is_nonempty_but_not_claimed_as_exchange_master():
    for market in ("Norge", "Sverige", "USA"):
        tickers = configured_universe_tickers(market)
        assert tickers
        rows = [{"ticker": ticker, "sector": "Technology", "data_fetch_status": "OK"} for ticker in tickers]
        contract = build_universe_contract(market, rows)
        assert contract["configured_universe_complete"] is True
        assert contract["coverage_pct"] == 100.0
        assert contract["source_authoritative_exchange_master"] is False
        assert "offisiell" in contract["source_disclaimer"]


def test_contract_reports_missing_symbol_and_metadata_without_hiding_it():
    tickers = configured_universe_tickers("Norge")
    rows = [{"ticker": ticker, "sector": "Technology", "data_fetch_status": "OK"} for ticker in tickers[:-1]]
    contract = build_universe_contract("Norge", rows)
    assert contract["coverage_failure"] is True
    assert contract["missing_symbols"] == [tickers[-1]]
    assert contract["metadata_completeness"]["market_cap"]["missing"]


def test_sector_balancing_reserves_breadth_without_mutating_scores():
    rows = [
        {"ticker": "A", "sector": "Technology", "stage1_prefilter_score": 99},
        {"ticker": "B", "sector": "Technology", "stage1_prefilter_score": 98},
        {"ticker": "C", "sector": "Financial Services", "stage1_prefilter_score": 80},
        {"ticker": "D", "sector": "Healthcare", "stage1_prefilter_score": 70},
    ]
    selected, audit = select_sector_balanced_rows(rows, 3)
    assert selected[0]["ticker"] == "A"
    assert "C" in {row["ticker"] for row in selected}
    assert [row["stage1_prefilter_score"] for row in rows] == [99, 98, 80, 70]
    assert "scorebonus" in audit["rule"]


def test_selection_trace_and_buy_gate_audit_explain_exclusion():
    rows = [{"ticker": "BAC", "market": "USA", "sector": "Financial Services", "stage1_prefilter_score": 88}]
    trace = build_selection_trace(rows, [], [])
    assert trace[0]["advanced"] is False
    assert trace[0]["exclusion_reason"]
    audit = build_buy_gate_audit([{
        "ticker": "BAC", "market": "USA", "sector": "Financial Services",
        "investment_score": 78.32, "risk_score": 20, "portfolio_action": "SKIP",
        "valid_for_decision": True, "evidence_valid_for_decision": False,
        "portfolio_decision": {"reason": "Evidensgrunnlaget er ikke komplett."},
    }], 78.0)
    assert audit[0]["score"] == 78.32
    assert audit[0]["buy_ready"] is False
    assert "evidens" in " ".join(audit[0]["all_blockers"]).lower()
