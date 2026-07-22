from datetime import datetime, timezone

from market_intelligence import (
    build_market_status,
    company_identity,
    diversify_portfolio,
    executive_intelligence,
    select_diverse_candidates,
)


def rows():
    return [
        {"ticker": "GOOG", "name": "Alphabet Inc. Class C", "market": "USA", "investment_score": 78.14},
        {"ticker": "GOOGL", "name": "Alphabet Inc. Class A", "market": "USA", "investment_score": 78.00},
        {"ticker": "DANSKE.CO", "name": "Danske Bank A/S", "market": "Danmark", "investment_score": 77.58},
        {"ticker": "MO", "name": "Altria Group, Inc.", "market": "USA", "investment_score": 77.55},
    ]


def test_top3_has_unique_companies():
    top3 = select_diverse_candidates(rows(), 3)
    assert [x["ticker"] for x in top3] == ["GOOG", "DANSKE.CO", "MO"]
    assert company_identity(rows()[0]) == company_identity(rows()[1])


def test_executive_intelligence_counts_unique_companies():
    info = executive_intelligence(rows())
    assert info["unique_companies"] == 3
    assert info["highest_score"] == 78.14
    assert info["markets_in_top10"] == 2


def test_portfolio_removes_duplicate_share_class_and_moves_weight_to_cash():
    proposal = {
        "allocations": [
            {"ticker": "GOOG", "name": "Alphabet Inc. Class C", "weight_pct": 2.5},
            {"ticker": "GOOGL", "name": "Alphabet Inc. Class A", "weight_pct": 2.4},
            {"ticker": "MO", "name": "Altria Group, Inc.", "weight_pct": 3.0},
        ],
        "invested_pct": 7.9,
        "cash_pct": 92.1,
    }
    result = diversify_portfolio(proposal)
    assert [x["ticker"] for x in result["allocations"]] == ["GOOG", "MO"]
    assert result["company_duplicates_removed"] == 1
    assert result["invested_pct"] == 5.5
    assert result["cash_pct"] == 94.5


def test_weekend_reason_is_consistent_across_timezones():
    sunday_late_utc = datetime(2026, 7, 19, 21, 25, tzinfo=timezone.utc)
    statuses = build_market_status(["USA", "Norge", "Finland"], now=sunday_late_utc)
    assert {x["reason"] for x in statuses} == {"Helg"}
