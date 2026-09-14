from __future__ import annotations

import math
import pandas as pd

from candidate_market_data import _technical_fields
from trend_intelligence import annotate_run, build_trend_receipt, VERSION


def _hist() -> pd.DataFrame:
    idx = pd.date_range("2025-09-01", periods=260, freq="B")
    prices = []
    p = 60.0
    for i in range(260):
        # Slow uptrend, then a visibly faster last 20 sessions.
        drift = 0.05 if i < 240 else 0.35
        p += drift + (0.08 * math.sin(i / 5.0))
        prices.append(p)
    volume = [100_000 + i * 80 for i in range(260)]
    for i in range(240, 260):
        volume[i] *= 1.8
    return pd.DataFrame({"Close": prices, "Volume": volume}, index=idx)


def test_enrichment_emits_breakout_obv_cross_and_acceleration_fields():
    fields, trace = _technical_fields(_hist())
    assert fields["return_5d"] > 0
    assert fields["return_20d"] > 0
    assert fields["momentum_acceleration_5v20"] is not None
    assert fields["price_vs_sma20_pct"] > 0
    assert fields["sma20_vs_sma50_pct"] > 0
    assert fields["sma50_vs_sma200_pct"] > 0
    assert fields["golden_cross_active"] is True
    assert fields["obv_pressure_10d"] > 0
    assert fields["obv_pressure_20d"] > 0
    assert len(fields["price_trend_60d"]) == 60
    assert "volume" in fields["price_trend_60d"][-1]


def test_early_signal_explains_why_strength_can_continue_without_authorising_trade():
    candidate = {
        "ticker": "TEST.OL", "market": "Norge", "sector": "Energy", "rank": 7,
        "investment_score": 69.0,
        "raw": {
            "return_5d": 5.0, "return_10d": 7.0, "return_20d": 10.0, "return_60d": 16.0,
            "momentum_acceleration_5v20": 2.5,
            "last_price": 110.0, "sma20": 104.0, "sma50": 98.0, "sma200": 90.0,
            "price_vs_sma20_pct": 5.77, "sma20_vs_sma50_pct": 6.12, "sma50_vs_sma200_pct": 8.89,
            "golden_cross_active": True, "golden_cross_age_sessions": 15,
            "rsi": 63.0, "rsi_cross_50_age_sessions": 4,
            "volume_ratio_20": 1.45, "obv_pressure_10d": 0.22, "obv_pressure_20d": 0.15,
            "breakout_20d": True, "breakout_20d_pct": 1.5,
            "breakout_60d": False, "breakout_60d_pct": -1.0,
            "distance_from_20d_high_pct": 0.0, "distance_from_60d_high_pct": -1.0,
            "price_trend_60d": [{"date": "2026-09-01", "close": 100.0, "volume": 100000}] * 20,
        },
    }
    receipt = build_trend_receipt(candidate, {})
    assert receipt["version"] == VERSION
    es = receipt["early_signal"]
    assert es["score"] >= 50
    codes = {x["code"] for x in es["signals"]}
    assert "ACCELERATION" in codes
    assert "BREAKOUT_20D" in codes
    assert "OBV_BUY_PRESSURE" in codes
    assert "RSI_HEALTHY_MOMENTUM" in codes
    assert es["descriptive_only"] is True
    assert receipt["descriptive_only"] is True


def test_annotate_run_builds_cross_sectional_relative_strength_and_watchlist():
    run = {
        "markets": ["Norge"],
        "candidates": [
            {"ticker": "FAST.OL", "market": "Norge", "sector": "Energy", "rank": 4, "investment_score": 68,
             "raw": {"return_5d": 5, "return_20d": 15, "return_60d": 25, "momentum_acceleration_5v20": 1.25,
                     "last_price": 120, "sma20": 110, "sma50": 100, "sma200": 90, "price_vs_sma20_pct": 9.1,
                     "sma20_vs_sma50_pct": 10, "sma50_vs_sma200_pct": 11.1, "golden_cross_active": True,
                     "rsi": 64, "volume_ratio_20": 1.5, "obv_pressure_10d": .2, "obv_pressure_20d": .15,
                     "breakout_20d": True, "breakout_20d_pct": 2}},
            {"ticker": "MID.OL", "market": "Norge", "sector": "Energy", "rank": 2, "investment_score": 75,
             "raw": {"return_5d": 1, "return_20d": 6, "return_60d": 8, "last_price": 105, "sma20": 103,
                     "sma50": 100, "sma200": 95, "price_vs_sma20_pct": 1.9, "sma20_vs_sma50_pct": 3,
                     "sma50_vs_sma200_pct": 5.3, "rsi": 57, "volume_ratio_20": 0.9}},
            {"ticker": "SLOW.OL", "market": "Norge", "sector": "Finance", "rank": 1, "investment_score": 80,
             "raw": {"return_5d": -1, "return_20d": 0, "return_60d": 2, "last_price": 100, "sma20": 100,
                     "sma50": 100, "sma200": 100, "rsi": 49, "volume_ratio_20": 1.0}},
        ],
    }
    annotate_run(run, {})
    fast = run["candidates"][0]["trend_receipt"]
    assert fast["market_rs_20d_percentile"] >= 75
    assert fast["sector_rs_20d_percentile"] > 70
    assert run["trend_discovery"]["early_signal_watchlist"][0]["ticker"] == "FAST.OL"
    assert run["trend_discovery"]["production_scoring_changed"] is False
    assert run["candidates"][0]["investment_score"] == 68


def test_hafnia_like_setup_is_flagged_strong_but_overbought_caution_is_preserved():
    candidate = {
        "ticker": "HAFNI.OL", "market": "Norge", "sector": "Industrials", "rank": 8,
        "raw": {
            "return_5d": 9.2, "return_10d": 10.8, "return_20d": 19.35, "return_60d": 20.54,
            "last_price": 84.8, "sma20": 75.86, "sma50": 72.95, "sma200": 68.81,
            "rsi": 74.7, "volume_ratio_20": 1.32,
            "distance_from_20d_high_pct": 0.0, "distance_from_60d_high_pct": 0.0,
        }
    }
    receipt = build_trend_receipt(candidate, {})
    es = receipt["early_signal"]
    assert es["score"] >= 80
    assert es["label"] == "STERKT TIDLIG STYRKESIGNAL"
    assert any("overkjøpt" in x for x in es["cautions"])
    assert any(x["code"] == "BREAKOUT_20D" for x in es["signals"])
    assert any(x["code"] == "GOLDEN_CROSS" for x in es["signals"])
