from alpha_radar_currency import market_cap_display
from alpha_radar_enrichment import enrich_alpha_radar_row
from alpha_radar_results import alpha_radar_result_to_print_html
from early_warning_engine import run_early_warning
from universe_engine import resolve_universe_tickers


def test_empty_news_does_not_create_fake_45_catalyst():
    def empty_news_provider(query, limit=8, source="manual"):
        return [], None

    enriched = enrich_alpha_radar_row(
        {"ticker": "NOEVID", "score": 6.2, "market_cap": 1_000_000_000},
        ticker="NOEVID",
        include_news=True,
        news_provider=empty_news_provider,
    )

    assert "small_news_big_impact_score" not in enriched
    assert "local_news_score" not in enriched
    assert enriched["news_count"] == 0

    result = run_early_warning(
        ["NOEVID"],
        limit=1,
        max_scan=1,
        include_news=True,
        score_provider=lambda ticker, use_news=False, include_insider=False: enriched,
    )
    assert result["candidates"] == []
    assert result.get("excluded_count", 0) >= 1 or result.get("market_counts", {}).get("Ekskludert", 0) >= 1


def test_market_cap_uses_dot_grouping_currency_and_nok_estimate_in_report():
    assert market_cap_display(193_407_647_744, "USD") == "193.407.647.744 USD"
    result = {
        "created_at": "2026-05-23 12:00",
        "scope": "USA",
        "mode": "Alpha Radar",
        "candidates": [
            {
                "rank": 1,
                "ticker": "BIG",
                "name": "Big Co",
                "market": "USA/annet",
                "hidden_potential_score": 51.0,
                "market_cap": 193_407_647_744,
                "market_cap_currency": "USD",
                "market_cap_nok_estimate": 2_030_780_301_312,
                "factor_quality": {},
            }
        ],
    }

    html = alpha_radar_result_to_print_html(result).decode("utf-8")
    assert "193.407.647.744 USD" in html
    assert "2.030.780.301.312 NOK" in html


def test_single_brazil_scope_can_request_more_than_old_25_cap():
    tickers = resolve_universe_tickers(["Brasil"], max_count=177)

    assert len(tickers) > 25
    assert all(ticker.endswith(".SA") for ticker in tickers)


