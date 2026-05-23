from early_warning_engine import run_early_warning


ROWS = {
    "REV.OL": {
        "ticker": "REV.OL",
        "name": "Revision Winner",
        "market": "Norge",
        "score": 6.8,
        "market_cap": 1_200_000_000,
        "estimate_revision_score": 0.82,
        "earnings_surprise_score": 0.76,
        "revenue_growth": 0.22,
        "profit_margin": 0.13,
        "ret_1m": 0.08,
        "ret_3m": 0.16,
        "score_parts": {"momentum": 0.78, "trend": 0.74, "volume": 0.72, "quality": 0.67},
        "insider_quality_score": 0.66,
        "macro_tailwind_score": 0.58,
    },
    "PRICE.ST": {
        "ticker": "PRICE.ST",
        "name": "Price Only",
        "market": "Sverige",
        "score": 7.1,
        "market_cap": 5_000_000_000,
        "ret_1m": 0.12,
        "ret_3m": 0.20,
        "score_parts": {"momentum": 0.86, "trend": 0.80, "volume": 0.76},
    },
}


def provider(ticker, use_news=False, include_insider=False):
    return ROWS.get(ticker)


def test_early_warning_ranks_expectation_change_above_price_only():
    result = run_early_warning(
        ["PRICE.ST", "REV.OL"],
        horizon="3m",
        limit=2,
        max_scan=2,
        score_provider=provider,
    )

    assert result["mode"] == "Early Warning V1"
    assert result["candidates"][0]["ticker"] == "REV.OL"
    assert result["candidates"][0]["factor_quality"]["expectation_change"] == "ekte"
    assert result["candidates"][1]["factor_scores"]["expectation_change"] is None
    assert result["scope_limits"]["listed_equities"] is True


def test_early_warning_emits_progress_events():
    events = []
    result = run_early_warning(
        ["REV.OL", "UNKNOWN.OL"],
        horizon="1m",
        limit=2,
        max_scan=2,
        score_provider=provider,
        progress_callback=events.append,
    )

    assert result["scanned_count"] == 2
    assert events[0]["status"] == "starter"
    assert events[-1]["status"] == "ferdig"
    assert any(event["status"] == "scoret" and event["ticker"] == "REV.OL" for event in events)
    assert any(event["status"] == "hoppet over" and event["ticker"] == "UNKNOWN.OL" for event in events)
