from __future__ import annotations

import market_intelligence as mi
from report_portfolio_intelligence import assert_portfolio_report_integrity, build_portfolio_report


def test_attempted_insider_search_cannot_be_counted_as_not_searched():
    rows = [{
        "ticker": "AAPL", "market": "USA",
        "decision_readiness": {"insider": "NOT_SEARCHED"},
        "raw": {"insider_intelligence": {
            "coverage": "CHECKED_NO_EVENTS",
            "search_log": [{"attempted": True, "status": "SUCCESS_NO_RESULTS"}],
        }},
    }]
    coverage = mi.insider_coverage_by_market(rows)[0]
    assert coverage["checked"] == 1
    assert coverage["no_events"] == 1
    assert coverage["not_searched"] == 0


def test_portfolio_contract_rejects_attempted_insider_labelled_not_searched():
    portfolio = {
        "positions": {"AAPL": {"ticker": "AAPL", "quantity": 1, "average_price": 100}},
        "cash": 900, "initial_cash": 1000,
    }
    candidate = {"ticker": "AAPL", "raw": {"insider_intelligence": {
        "coverage": "NOT_SEARCHED", "search_log": [{"attempted": True, "status": "SUCCESS_NO_RESULTS"}],
    }}}
    report = build_portfolio_report(portfolio, [candidate])
    try:
        assert_portfolio_report_integrity(report)
    except RuntimeError as exc:
        assert "innsider er kontrollert" in str(exc)
    else:
        raise AssertionError("Selvmotsigende innsiderstatus skulle blokkert rapporten")
