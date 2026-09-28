from __future__ import annotations

from super_portfolio import (
    SuperPortfolioConfig,
    _automatic_stop_exit,
    _stop_status,
    dynamic_stop_levels,
)


def test_inve_example_enters_profit_protection_exit_now() -> None:
    cfg = SuperPortfolioConfig()
    position = {
        "ticker": "INVE-A.ST",
        "entry_price": 395.60,
        "peak_price": 408.50,
        "last_price": 401.40,
    }
    position.update(_stop_status(position, cfg))

    assert position["peak_gain_pct"] == 3.26
    assert position["profit_protection_active"] is True
    assert position["profit_retention_pct"] == 55.0
    assert position["protected_gain_pct"] == 1.79
    assert position["profit_floor_price"] > 402.0
    assert position["hard_stop_price"] == position["profit_floor_price"]
    assert position["stop_status"] == "STOP TRIGGERED"
    assert position["stop_mode"] == "PROFIT_PROTECT"
    decision = _automatic_stop_exit(position)
    assert decision is not None
    assert decision[0] == "PROFIT_PROTECTION_EXIT"


def test_profit_protection_is_not_active_before_two_percent_mfe() -> None:
    cfg = SuperPortfolioConfig()
    levels = dynamic_stop_levels(
        {"entry_price": 100.0, "peak_price": 101.9, "last_price": 101.0},
        cfg,
    )
    assert levels["peak_gain_pct"] == 1.9
    assert levels["profit_protection_active"] is False
    assert levels["profit_floor_price"] == 0.0
    assert levels["hard_stop_drawdown_pct"] == 3.0


def test_profit_retention_tightens_as_peak_gain_grows() -> None:
    cfg = SuperPortfolioConfig()
    cases = [
        (102.5, 40.0, 1.0),
        (104.0, 55.0, 2.2),
        (106.0, 65.0, 3.9),
        (110.0, 70.0, 7.0),
    ]
    for peak, retention, protected in cases:
        levels = dynamic_stop_levels({"entry_price": 100.0, "peak_price": peak}, cfg)
        assert levels["profit_retention_pct"] == retention
        assert levels["protected_gain_pct"] == protected


def test_exit_watch_can_secure_profit_before_floor_break_on_confirmed_fall() -> None:
    cfg = SuperPortfolioConfig()
    position = {
        "ticker": "TEST",
        "entry_price": 100.0,
        "peak_price": 105.0,
        "last_price": 103.7,
    }
    position.update(_stop_status(position, cfg))
    assert position["stop_status"] == "EXIT WATCH"
    position["stop_direction_arrow"] = "↓"
    decision = _automatic_stop_exit(position)
    assert decision is not None
    assert decision[0] == "CONFIRMED_PROFIT_PROTECTION_EXIT"


def test_exit_metrics_measure_mfe_given_back_and_retained() -> None:
    cfg = SuperPortfolioConfig()
    position = {"entry_price": 100.0, "peak_price": 105.0, "last_price": 104.0}
    position.update(_stop_status(position, cfg))
    assert position["peak_gain_pct"] == 5.0
    assert position["pnl_pct"] == 4.0
    assert position["profit_giveback_pct"] == 1.0
    assert position["mfe_retained_pct"] == 80.0
