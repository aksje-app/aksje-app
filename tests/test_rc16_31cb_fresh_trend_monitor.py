from datetime import datetime, timezone

import fresh_trend_monitor as ftm


def receipt(ticker="TEST.OL", score=68, hold=1, volume=1.4, accel=1.2, r3=2.0):
    return {
        "ticker": ticker, "fresh_signal": {"score": score, "trend_age_sessions": 1, "trend_age": "NY"},
        "breakout_20d": True, "breakout_holding": True, "breakout_hold_sessions": hold,
        "last_price": 101.0, "prior_20d_high": 100.0, "sma20": 98.0,
        "volume_ratio_20": volume, "momentum_acceleration_3v20": accel,
        "return_3d_pct": r3, "market_rs_5d_percentile": 80, "sector_rs_5d_percentile": 75,
        "rsi": 62,
    }


def test_score_path_and_positive_status_progression(monkeypatch):
    monkeypatch.setattr(ftm, "write_json", lambda *args, **kwargs: None)
    now = datetime(2026, 9, 7, 9, 0, tzinfo=timezone.utc)
    first = ftm.monitor_receipts([receipt(score=68)], now=now, state={}, notify=False)
    row1 = first["watchlist"][0]
    assert row1["status"] in {"NYTT", "AKSELERERER"}
    second = ftm.monitor_receipts([receipt(score=79, hold=2, accel=2.0)], now=now, state=first, notify=False)
    third = ftm.monitor_receipts([receipt(score=91, hold=3, volume=1.8, accel=2.5)], now=now, state=second, notify=False)
    row3 = third["watchlist"][0]
    assert row3["score_path"] == [68.0, 79.0, 91.0]
    assert row3["status"] == "STERKT BEKREFTET"
    assert set(row3["components"]) >= {"Freshness", "Confirmation", "Velocity", "Risk"}


def test_negative_transition_emits_alert(monkeypatch):
    monkeypatch.setattr(ftm, "write_json", lambda *args, **kwargs: None)
    now = datetime(2026, 9, 7, 10, 0, tzinfo=timezone.utc)
    old = {"tracked": {"TEST.OL": {"ticker": "TEST.OL", "status": "AKSELERERER", "score": 79,
            "score_path": [68, 79], "first_seen_at": now.isoformat()}}}
    weak = receipt(score=42, hold=0, volume=.6, accel=-2, r3=-4)
    weak.update({"breakout_holding": False, "last_price": 97})
    result = ftm.monitor_receipts([weak], now=now, state=old, notify=False)
    assert result["watchlist"][0]["status"] == "FALSKT BREAKOUT"
    assert result["alerts"][0]["status"] == "FALSKT BREAKOUT"


def test_monitor_is_observational(monkeypatch):
    monkeypatch.setattr(ftm, "write_json", lambda *args, **kwargs: None)
    result = ftm.monitor_receipts([receipt()], state={}, notify=False)
    assert result["production_scoring_changed"] is False
    assert result["trade_authority"] is False

