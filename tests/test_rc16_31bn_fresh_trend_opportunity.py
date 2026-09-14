from __future__ import annotations

import math
from pathlib import Path

import pandas as pd

from candidate_market_data import _technical_fields
from trend_intelligence import annotate_run, build_opportunity_preview, build_trend_receipt, should_escalate_evidence, VERSION


def _fresh_hist() -> pd.DataFrame:
    idx = pd.date_range("2025-09-01", periods=260, freq="B")
    close=[]; high=[]; low=[]; volume=[]
    p=70.0
    for i in range(260):
        # quiet/compressed period, then a 5-session ignition with rising volume
        if i < 245:
            p += 0.02 + 0.05 * math.sin(i/6)
        elif i < 255:
            p += 0.08 + 0.02 * math.sin(i)
        else:
            p += 1.10
        close.append(p); high.append(p*1.006); low.append(p*0.994)
        volume.append(100_000 if i < 255 else 220_000 + (i-255)*20_000)
    return pd.DataFrame({"Close":close,"High":high,"Low":low,"Volume":volume}, index=idx)


def test_fresh_enrichment_contains_hafnia_style_first_signals():
    fields,_ = _technical_fields(_fresh_hist())
    for key in ("return_1d","return_3d","return_5d","return_15d","sma20_slope_5d_pct","golden_cross_spread_change_10d_pp","rsi_cross_60_age_sessions","compression_ratio_10v40","volatility_expansion_5v20","support_levels","resistance_levels"):
        assert key in fields
    assert fields["return_3d"] > 0
    assert fields["sma20_slope_5d_pct"] is not None
    assert isinstance(fields["support_levels"], list)


def test_new_trend_is_separate_from_old_winner():
    new = {"ticker":"NEW.OL","market":"Norge","sector":"Tech","rank":12,"data_quality":95,"raw":{
        "return_1d":2.0,"return_3d":5.2,"return_5d":6.4,"return_20d":7.0,"return_60d":8.0,
        "momentum_acceleration_3v20":4.15,"momentum_acceleration_5v20":4.65,"rsi":61,
        "rsi_cross_50_age_sessions":2,"rsi_cross_60_age_sessions":1,"rsi_10d_breakout":True,
        "breakout_20d":True,"breakout_holding":True,"breakout_20d_age_sessions":2,"breakout_hold_sessions":3,
        "volume_ratio_20":1.8,"obv_pressure_5d":0.25,"obv_pressure_10d":0.18,
        "sma20_slope_5d_pct":0.8,"compression_ratio_10v40":0.45,"volatility_expansion_5v20":1.4,
        "last_price":110,"sma20":104,"sma50":102,"sma200":100,
    }}
    old = {"ticker":"OLD.OL","market":"Norge","sector":"Energy","rank":1,"data_quality":95,"raw":{
        "return_1d":0.1,"return_3d":0.4,"return_5d":0.7,"return_20d":18,"return_60d":40,
        "momentum_acceleration_3v20":-2.3,"momentum_acceleration_5v20":-3.8,"rsi":68,
        "golden_cross_active":True,"golden_cross_age_sessions":45,"volume_ratio_20":0.9,
        "last_price":140,"sma20":135,"sma50":120,"sma200":100,
    }}
    run={"markets":["Norge"],"candidates":[new,old]}
    annotate_run(run,{})
    assert run["trend_discovery"]["fresh_trend_watchlist"][0]["ticker"] == "NEW.OL"
    assert all(x["ticker"] != "OLD.OL" for x in run["trend_discovery"]["fresh_trend_watchlist"])
    assert any(x["ticker"] == "OLD.OL" for x in run["trend_discovery"]["established_trend_watchlist"])


def test_fresh_signal_escalates_research_without_buy_authority():
    c={"ticker":"IGNITE.OL","market":"Norge","sector":"Industrials","data_quality":95,"raw":{
        "return_3d":4.5,"return_5d":6,"return_20d":7,"momentum_acceleration_3v20":3.45,"momentum_acceleration_5v20":4.25,
        "breakout_20d":True,"breakout_holding":True,"breakout_20d_age_sessions":1,"breakout_hold_sessions":2,
        "volume_ratio_20":1.6,"obv_pressure_5d":0.2,"rsi":59,"rsi_cross_50_age_sessions":2,
        "last_price":105,"sma20":100,"sma50":99,"sma200":98,"sma20_slope_5d_pct":0.6,
    }}
    preview=build_opportunity_preview(c)
    assert preview["fresh_signal"]["score"] >= 55
    assert should_escalate_evidence(c) is True
    assert preview["descriptive_only"] is True


def test_relative_strength_ignition_flags_fast_improvement():
    run={"markets":["Norge"],"candidates":[
        {"ticker":"A.OL","market":"Norge","sector":"Tech","raw":{"return_5d":8,"return_20d":5,"return_60d":6,"return_3d":5,"last_price":110,"sma20":104,"sma50":103,"sma200":100,"rsi":62,"breakout_20d":True,"breakout_20d_age_sessions":2,"volume_ratio_20":1.5}},
        {"ticker":"B.OL","market":"Norge","sector":"Tech","raw":{"return_5d":1,"return_20d":10,"return_60d":15,"last_price":110,"sma20":105,"sma50":100,"sma200":95,"rsi":60}},
        {"ticker":"C.OL","market":"Norge","sector":"Finance","raw":{"return_5d":0,"return_20d":7,"return_60d":9,"last_price":100,"sma20":100,"sma50":99,"sma200":98,"rsi":52}},
    ]}
    annotate_run(run,{})
    a=run["candidates"][0]["trend_receipt"]
    assert a["relative_strength_ignition"] > 0
    assert any(x.get("code") == "RS_IGNITION" for x in a["fresh_signal"]["signals"])


def test_hafnia_screenshot_features_are_represented_in_receipt():
    c={"ticker":"HAFNI.OL","market":"Norge","sector":"Industrials","raw":{
        "return_1d":2.2,"return_5d":9.2,"return_15d":16.4,"return_20d":19.35,"return_60d":31.0,
        "rsi":74.7,"rsi_cross_50_age_sessions":6,"rsi_10d_breakout":True,
        "obv_pressure_5d":0.15,"obv_pressure_10d":0.17,"obv_pressure_20d":0.13,
        "golden_cross_active":True,"golden_cross_spread_change_10d_pp":0.7,
        "breakout_20d":True,"breakout_holding":True,"breakout_20d_age_sessions":1,"breakout_hold_sessions":2,
        "support_levels":[82.0,80.25,77.95,75.75],"resistance_levels":[87.4,90.0,91.95],
        "volume_ratio_20":1.4,"last_price":84.8,"sma20":75.8,"sma50":72,"sma200":68,
    }}
    r=build_trend_receipt(c,{})
    assert r["return_15d_pct"] == 16.4
    assert r["rsi_10d_breakout"] is True
    assert r["support_levels"][:2] == [82.0,80.25]
    assert r["resistance_levels"][0] == 87.4
    assert r["breakout_hold_sessions"] == 2
    assert any("overkjøpt" in x for x in r["fresh_signal"]["cautions"])


def test_pipeline_source_reserves_fresh_evidence_lane():
    src=Path("investment_pipeline.py").read_text(encoding="utf-8")
    assert "EARLY_SIGNAL_CRITICAL" in src
    assert "FRESH_TREND_ACCELERATION" in src
    assert "fresh_signal_reserved_slot" in src
    assert "areas\": [\"news\", \"insider\", \"short\"]" in src
    assert VERSION.endswith("31bn")
