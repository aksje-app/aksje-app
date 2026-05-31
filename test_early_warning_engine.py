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
        "articles": [{"title": "Revision Winner contract", "source": "NewsWeb", "url": "https://example.com/rev-news"}],
        "latest_transactions": [{"name": "Kari CEO", "relation": "CEO", "type": "BUY", "url": "https://example.com/rev-insider"}],
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
        "articles": [{"title": "Price Only market update", "source": "Placera", "url": "https://example.com/price-news"}],
        "latest_transactions": [{"name": "Board Member", "relation": "Director", "type": "BUY", "url": "https://example.com/price-insider"}],
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
    assert "fresh_source_evidence" in result["candidates"][0]["factor_scores"]
    assert result["candidates"][1]["factor_scores"]["expectation_change"] is None
    assert result["scope_limits"]["listed_equities"] is True
    assert ".OL" in result["scope_limits"]["euronext_note"]


def test_early_warning_keeps_source_evidence_details():
    def evidence_provider(ticker, use_news=False, include_insider=False):
        row = dict(ROWS["REV.OL"])
        row["ticker"] = ticker
        row["articles"] = [{
            "title": "Kontrakt vunnet",
            "source": "Borsmelding",
            "published": "2026-05-22",
            "url": "https://example.com/news",
        }]
        row["latest_transactions"] = [{
            "name": "Kari CEO",
            "relation": "CEO",
            "type": "BUY",
            "date": "2026-05-21",
            "shares": 10000,
            "url": "https://example.com/insider",
        }]
        return row

    result = run_early_warning(["REV.OL"], limit=1, max_scan=1, score_provider=evidence_provider)
    candidate = result["candidates"][0]

    assert candidate["evidence_items"]
    assert candidate["news_evidence"][0]["url"] == "https://example.com/news"
    assert candidate["insider_evidence"][0]["title"] == "Kari CEO"


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


def test_early_warning_balanced_market_output_keeps_non_us_visible():
    rows = {}
    for idx in range(1, 5):
        rows[f"US{idx}"] = {
            **ROWS["PRICE.ST"],
            "ticker": f"US{idx}",
            "market": "USA/annet",
            "score": 8.5 - idx / 10,
            "ret_1m": 0.18,
            "ret_3m": 0.25,
        }
    rows["REV.OL"] = ROWS["REV.OL"]
    rows["PRICE.ST"] = ROWS["PRICE.ST"]

    def mixed_provider(ticker, use_news=False, include_insider=False):
        return rows.get(ticker)

    result = run_early_warning(
        ["US1", "US2", "US3", "US4", "REV.OL", "PRICE.ST"],
        horizon="3m",
        limit=3,
        max_scan=6,
        score_provider=mixed_provider,
        balance_markets=True,
    )

    tickers = [row["ticker"] for row in result["candidates"]]
    assert any(ticker.endswith(".OL") or ticker.endswith(".ST") for ticker in tickers)
    assert result["market_balance_enabled"] is True
    assert result["market_scan_counts"]["USA/annet"] == 4
    assert result["market_candidate_counts"]["Norge"] >= 1 or result["market_candidate_counts"]["Sverige"] >= 1






