from services.value_empirical_dataset_audit import audit_empirical_backtest_dataset


def row():
    return {"ticker": "TEST.OL", "snapshot_date": "2024-01-10",
            "fundamentals_known_at": "2024-01-04", "price_date": "2024-01-10",
            "outcome_date": "2024-02-22", "forward_return_pct": 5,
            "historical_universe_member": True, "fundamentals_source": "archived filing",
            "filing_reference": "report-2023-Q3", "historical_universe_source": "archived index",
            "price_source": "adjusted daily series"}


def test_strict_metadata_acceptance_is_only_manual_review():
    result = audit_empirical_backtest_dataset([row()], as_of="2024-04-01")
    assert result["status"] == "READY_FOR_MANUAL_REVIEW"
    assert result["can_authorize_buy"] is False


def test_missing_filing_origin_fails_closed():
    item = {**row(), "filing_reference": ""}
    result = audit_empirical_backtest_dataset([item], as_of="2024-04-01")
    assert result["status"] == "BACKTEST_NOT_VERIFIABLE"
    assert result["rejection_counts"]["MISSING_DISCLOSURE_REFERENCE"] == 1


def test_future_outcome_cannot_be_used():
    result = audit_empirical_backtest_dataset([row()], as_of="2024-02-01")
    assert result["rejection_counts"]["UNMATURED_OUTCOME"] == 1
