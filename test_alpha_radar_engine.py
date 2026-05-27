from alpha_radar_engine import normalize_alpha_radar_parameters, run_alpha_radar


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
    "STB.OL": {
        "ticker": "STB.OL",
        "name": "Storebrand ASA",
        "score": 7.5,
        "ret_1m": 0.04,
        "ret_3m": 0.08,
        "ret_6m": 0.16,
        "volatility": 0.018,
        "max_drawdown": -0.10,
        "market_cap": 33_000_000_000,
        "catalyst_score": 0.68,
        "score_parts": {
            "momentum": 0.65,
            "trend": 0.70,
            "quality": 0.78,
            "fundamental_growth": 0.70,
            "debt": 0.70,
            "value": 0.62,
            "volume": 0.62,
        },
    },
    "XXL.OL": {
        "ticker": "XXL.OL",
        "name": "XXL ASA",
        "score": 5.5,
        "ret_1m": 0.03,
        "ret_3m": 0.06,
        "ret_6m": -0.04,
        "volatility": 0.045,
        "max_drawdown": -0.30,
        "market_cap": 2_200_000_000,
        "catalyst_score": 0.58,
        "score_parts": {
            "momentum": 0.56,
            "trend": 0.54,
            "quality": 0.42,
            "fundamental_growth": 0.42,
            "debt": 0.38,
            "value": 0.64,
            "volume": 0.58,
        },
    },
    "MICRO.OL": {
        "ticker": "MICRO.OL",
        "name": "Real Micro Cap",
        "score": 6.6,
        "ret_1m": 0.05,
        "ret_3m": 0.08,
        "ret_6m": 0.02,
        "volatility": 0.026,
        "max_drawdown": -0.14,
        "market_cap": 450_000_000,
        "catalyst_score": 0.60,
        "score_parts": {
            "momentum": 0.61,
            "trend": 0.60,
            "quality": 0.58,
            "fundamental_growth": 0.56,
            "debt": 0.56,
            "value": 0.68,
            "volume": 0.60,
        },
    },
    "UNKNOWNCAP.OL": {
        "ticker": "UNKNOWNCAP.OL",
        "name": "Unknown Cap",
        "score": 6.4,
        "ret_1m": 0.04,
        "ret_3m": 0.07,
        "ret_6m": 0.05,
        "volatility": 0.022,
        "max_drawdown": -0.12,
        "catalyst_score": 0.62,
        "score_parts": {
            "momentum": 0.62,
            "trend": 0.60,
            "quality": 0.56,
            "fundamental_growth": 0.55,
            "debt": 0.55,
            "value": 0.62,
            "volume": 0.59,
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
        precision_level="Utforskende",
        market_cap_filter="Alle",
        score_provider=fake_score_provider,
    )

    assert len(result["candidates"]) == 4
    assert result["low_data_count"] == 3
    assert any("lav-data" in row["manual_review"].lower() for row in result["candidates"])


def test_alpha_radar_v2_excludes_crowded_large_caps_from_hidden_small_mid():
    result = run_alpha_radar(
        ["MEGA", "QUIET.CO"],
        horizon="6m",
        limit=2,
        mode="Skjulte small/mid caps",
        score_provider=fake_score_provider,
    )

    tickers = [row["ticker"] for row in result["candidates"]]
    assert tickers == ["QUIET.CO"]
    assert result["market_cap_filter"] == "Small/mid"
    assert result["excluded_reason_counts"]["for stor borsverdi for Small/mid"] == 1
    assert any(row["ticker"] == "MEGA" for row in result["excluded_samples"])


def test_alpha_radar_blocks_stb_and_xxl_from_micro_small_gate():
    result = run_alpha_radar(
        ["STB.OL", "XXL.OL", "MICRO.OL"],
        horizon="3m",
        limit=3,
        max_scan=3,
        market_cap_filter="Mikro/small",
        score_provider=fake_score_provider,
    )

    tickers = [row["ticker"] for row in result["candidates"]]
    assert tickers == ["MICRO.OL"]
    assert result["excluded_reason_counts"]["for stor borsverdi for Mikro/small"] == 2
    assert {row["ticker"] for row in result["excluded_samples"]} >= {"STB.OL", "XXL.OL"}


def test_alpha_radar_blocks_unknown_market_cap_in_strict_size_gates():
    result = run_alpha_radar(
        ["UNKNOWNCAP.OL"],
        horizon="3m",
        limit=1,
        market_cap_filter="Small/mid",
        score_provider=fake_score_provider,
    )

    assert result["candidates"] == []
    assert result["excluded_reason_counts"]["ukjent borsverdi blokkert for Small/mid"] == 1
    assert result["excluded_reason_counts"]["ukjent borsverdi blokkert i Streng presisjon"] == 1


def test_alpha_radar_does_not_fill_low_data_inside_strict_cap_filter():
    result = run_alpha_radar(
        ["UNKNOWN1.OL"],
        horizon="3m",
        limit=1,
        market_cap_filter="Mikro/small",
        precision_level="Utforskende",
        fill_low_data=True,
        score_provider=fake_score_provider,
    )

    assert result["candidates"] == []
    assert result["effective_parameters"]["fill_low_data"] is False
    assert result["excluded_reason_counts"]["mangler analysedata"] == 1
    assert any("lav-data utfylling" in warning for warning in result["parameter_warnings"])


def test_alpha_radar_normalizes_impossible_parameter_combinations():
    params = normalize_alpha_radar_parameters(
        mode="Skjulte small/mid caps",
        market_cap_filter="Kun large/mega",
        precision_level="Streng",
        active_signals=[
            "Borsverdi",
            "Nyheter/katalysator",
            "Resultater",
            "Insider/bjellesauer",
            "Ravarer/makro",
        ],
        fill_low_data=True,
    )

    assert params["market_cap_filter"] == "Small/mid"
    assert params["fill_low_data"] is False
    assert len(params["active_signals"]) == 3
    joined = " ".join(params["parameter_warnings"])
    assert "Kun large/mega" in joined
    assert "Signal-lupe" in joined
    assert "lav-data" in joined


def test_alpha_radar_emits_progress_events_for_ui():
    events = []

    result = run_alpha_radar(
        ["MICRO.OL", "STB.OL", "UNKNOWNCAP.OL"],
        horizon="3m",
        limit=2,
        max_scan=3,
        market_cap_filter="Mikro/small",
        score_provider=fake_score_provider,
        progress_callback=events.append,
    )

    assert result["scanned_count"] == 3
    assert events[0]["status"] == "starter"
    assert events[-1]["status"] == "ferdig"
    assert events[-1]["completed"] == 3
    assert any(event["status"] == "scoret" and event["ticker"] == "MICRO.OL" for event in events)
    assert any(event["status"] == "ekskludert" and event["ticker"] == "STB.OL" for event in events)


def test_alpha_radar_balanced_market_output_keeps_non_us_visible():
    rows = {}
    for idx in range(1, 5):
        rows[f"USA{idx}"] = {
            **FAKE_ROWS["QUAL.ST"],
            "ticker": f"USA{idx}",
            "name": f"USA Winner {idx}",
            "market_cap": 8_000_000_000,
            "score": 8.8 - idx / 10,
            "ret_1m": 0.18,
            "ret_3m": 0.24,
        }
    rows["NORDIC.OL"] = {**FAKE_ROWS["MOM.OL"], "ticker": "NORDIC.OL", "score": 6.8}
    rows["SWED.ST"] = {**FAKE_ROWS["QUAL.ST"], "ticker": "SWED.ST", "score": 6.7}

    def provider(ticker, use_news=False, include_insider=False):
        return rows.get(ticker)

    result = run_alpha_radar(
        ["USA1", "USA2", "USA3", "USA4", "NORDIC.OL", "SWED.ST"],
        horizon="3m",
        limit=3,
        max_scan=6,
        score_provider=provider,
        balance_markets=True,
    )

    tickers = [row["ticker"] for row in result["candidates"]]
    assert any(ticker.endswith(".OL") or ticker.endswith(".ST") for ticker in tickers)
    assert result["market_balance_enabled"] is True
    assert result["market_scan_counts"]["USA/annet"] == 4
    assert result["market_scan_counts"]["Norge"] == 1
    assert result["market_candidate_counts"]["Norge"] >= 1 or result["market_candidate_counts"]["Sverige"] >= 1

