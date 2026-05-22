from alpha_radar_engine import run_alpha_radar


FAKE_ROWS = {
    "MOM.OL": {
        "ticker": "MOM.OL",
        "name": "Momentum Nordic",
        "score": 7.1,
        "ret_1m": 0.24,
        "ret_3m": 0.16,
        "ret_6m": 0.05,
        "volatility": 0.032,
        "max_drawdown": -0.18,
        "market_cap": 2_400_000_000,
        "catalyst_score": 0.88,
        "insider_score": 0.52,
        "score_parts": {
            "momentum": 0.88,
            "trend": 0.82,
            "quality": 0.48,
            "fundamental_growth": 0.48,
            "debt": 0.55,
            "value": 0.42,
            "volume": 0.86,
        },
    },
    "QUAL.ST": {
        "ticker": "QUAL.ST",
        "name": "Quality Sweden",
        "score": 7.6,
        "ret_1m": 0.025,
        "ret_3m": 0.075,
        "ret_6m": 0.18,
        "volatility": 0.015,
        "max_drawdown": -0.08,
        "market_cap": 4_000_000_000,
        "catalyst_score": 0.62,
        "insider_score": 0.70,
        "forward_pe": 16,
        "score_parts": {
            "momentum": 0.62,
            "trend": 0.68,
            "quality": 0.86,
            "fundamental_growth": 0.82,
            "debt": 0.78,
            "value": 0.72,
            "volume": 0.58,
        },
    },
    "QUIET.CO": {
        "ticker": "QUIET.CO",
        "name": "Quiet Denmark",
        "score": 6.3,
        "ret_1m": 0.04,
        "ret_3m": 0.09,
        "ret_6m": 0.11,
        "volatility": 0.021,
        "max_drawdown": -0.14,
        "market_cap": 650_000_000,
        "news_count": 1,
        "analyst_count": 2,
        "catalyst_score": 0.66,
        "insider_score": 0.64,
        "score_parts": {
            "momentum": 0.67,
            "trend": 0.66,
            "quality": 0.62,
            "fundamental_growth": 0.66,
            "debt": 0.63,
            "value": 0.64,
            "volume": 0.64,
        },
    },
    "RISK.HE": {
        "ticker": "RISK.HE",
        "name": "Risk Finland",
        "score": 7.4,
        "ret_1m": 0.18,
        "ret_3m": 0.22,
        "ret_6m": -0.05,
        "volatility": 0.075,
        "max_drawdown": -0.44,
        "market_cap": 700_000_000,
        "catalyst_score": 0.78,
        "score_parts": {
            "momentum": 0.82,
            "trend": 0.60,
            "quality": 0.38,
            "fundamental_growth": 0.36,
            "debt": 0.34,
            "value": 0.50,
            "volume": 0.80,
        },
    },
    "MEGA": {
        "ticker": "MEGA",
        "name": "Mega Covered",
        "score": 8.9,
        "ret_1m": 0.06,
        "ret_3m": 0.12,
        "ret_6m": 0.20,
        "ret_1y": 0.42,
        "volatility": 0.018,
        "max_drawdown": -0.07,
        "market_cap": 420_000_000_000,
        "news_count": 18,
        "analyst_count": 32,
        "catalyst_score": 0.72,
        "score_parts": {
            "momentum": 0.78,
            "trend": 0.76,
            "quality": 0.84,
            "fundamental_growth": 0.76,
            "debt": 0.70,
            "value": 0.44,
            "volume": 0.72,
        },
    },
}


def fake_score_provider(ticker, use_news=False, include_insider=False):
    return FAKE_ROWS.get(ticker)


def test_alpha_radar_returns_limited_manual_review_shortlist():
    result = run_alpha_radar(
        ["MOM.OL", "QUAL.ST", "QUIET.CO", "RISK.HE"],
        horizon="3m",
        limit=3,
        max_scan=4,
        include_insider=True,
        score_provider=fake_score_provider,
    )

    candidates = result["candidates"]
    assert len(candidates) == 3
    assert candidates[0]["rank"] == 1
    assert candidates[0]["alpha_score"] >= candidates[1]["alpha_score"]
    assert all(row["manual_review"].startswith("Manuell sjekk") for row in candidates)
    assert all(row["signals"] for row in candidates)
    assert all(row["why_now"] for row in candidates)
    assert all("factor_scores" in row for row in candidates)
    assert "automatisk handel" in result["disclaimer"]


def test_alpha_radar_horizon_changes_ranking_bias():
    one_month = run_alpha_radar(
        ["MOM.OL", "QUAL.ST", "QUIET.CO"],
        horizon="1m",
        limit=1,
        score_provider=fake_score_provider,
    )
    twelve_month = run_alpha_radar(
        ["MOM.OL", "QUAL.ST", "QUIET.CO"],
        horizon="12m",
        limit=1,
        include_insider=True,
        score_provider=fake_score_provider,
    )

    assert one_month["candidates"][0]["ticker"] == "MOM.OL"
    assert twelve_month["candidates"][0]["ticker"] == "QUIET.CO"


def test_alpha_radar_v2_fills_requested_count_with_low_data_hypotheses():
    result = run_alpha_radar(
        ["MOM.OL", "UNKNOWN1.OL", "UNKNOWN2.ST", "UNKNOWN3.CO"],
        horizon="3m",
        limit=4,
        max_scan=4,
        fill_low_data=True,
        score_provider=fake_score_provider,
    )

    assert len(result["candidates"]) == 4
    assert result["low_data_count"] == 3
    assert any("lav-data" in row["manual_review"].lower() for row in result["candidates"])


def test_alpha_radar_v2_penalizes_crowded_large_caps():
    result = run_alpha_radar(
        ["MEGA", "QUIET.CO"],
        horizon="6m",
        limit=2,
        mode="Skjulte small/mid caps",
        score_provider=fake_score_provider,
    )

    tickers = [row["ticker"] for row in result["candidates"]]
    assert tickers[0] == "QUIET.CO"
    mega = next(row for row in result["candidates"] if row["ticker"] == "MEGA")
    assert mega["crowdedness_penalty"] >= 20
    assert any("overdekket" in reason for reason in mega["reject_reasons"])
