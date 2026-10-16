from services.value_session_evidence import (
    audit_historical_session_evidence, research_with_session_evidence,
)


def row(ticker, cohort, ret, horizon=7):
    return {
        "ticker": ticker, "cohort": cohort, "horizon_sessions": horizon,
        "observed_trading_sessions": horizon, "exchange_calendar_source": "XOSL 2024 exchange calendar",
        "price_adjusted_for_corporate_actions": True,
        "price_adjustment_source": "archived adjusted daily prices",
        "snapshot_date": "2024-02-01", "price_date": "2024-02-01",
        "fundamentals_known_at": "2024-01-25",
        "fundamentals_first_published_at": "2024-01-24",
        "outcome_date": "2024-03-20", "forward_return_pct": ret,
        "historical_universe_member": True, "fundamentals_source": "filings",
        "filing_reference": "issuer-2023-Q3", "historical_universe_source": "archived exchange list",
        "price_source": "adjusted prices",
    }


def test_verified_metadata_allows_descriptive_research_only():
    result = research_with_session_evidence(
        [row("A", "value_shadow", -5), row("B", "legacy_finalist", 2)],
        as_of="2024-04-01",
    )
    assert result["status"] == "DESCRIPTIVE_RESEARCH_ONLY"
    assert result["session_evidence"]["status"] == "READY_FOR_MANUAL_SOURCE_VERIFICATION"
    assert result["can_authorize_buy"] is False


def test_calendar_days_cannot_replace_trading_sessions():
    item = row("A", "value_shadow", 4)
    item["observed_trading_sessions"] = 6
    result = research_with_session_evidence([item], as_of="2024-04-01")
    assert result["status"] == "BACKTEST_NOT_VERIFIABLE"
    assert "UNVERIFIED_TRADING_SESSION_COUNT" in result["session_evidence"]["rejection_counts"]


def test_missing_adjustment_and_first_publication_rejected():
    item = row("A", "value_shadow", 3)
    item["price_adjusted_for_corporate_actions"] = False
    item["fundamentals_first_published_at"] = "2024-02-05"
    problems = audit_historical_session_evidence([item])["rejection_counts"]
    assert "UNVERIFIED_ADJUSTED_RETURN" in problems
    assert "UNVERIFIED_FIRST_PUBLICATION" in problems


def test_invalid_return_and_empty_rows_fail_closed():
    item = row("A", "value_shadow", float("nan"))
    assert "INVALID_RETURN" in audit_historical_session_evidence([item])["rejection_counts"]
    assert audit_historical_session_evidence([])["status"] == "BACKTEST_NOT_VERIFIABLE"
