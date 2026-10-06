from __future__ import annotations

from pathlib import Path

from paper_risk_policy import strict_profit_protection_levels

ROOT = Path(__file__).resolve().parents[1]


def test_paper_strict_stop_is_three_percent() -> None:
    levels = strict_profit_protection_levels({"entry_price": 100, "highest_price": 100, "last_price": 97})
    assert levels["hard_stop_drawdown_pct"] == 3.0
    assert levels["effective_stop_price"] == 97.0
    assert levels["stop_status"] == "STOP TRIGGERED"


def test_paper_uses_same_mfe_tiers_as_super() -> None:
    levels = strict_profit_protection_levels({"entry_price": 100, "highest_price": 104, "last_price": 102})
    assert levels["peak_gain_pct"] == 4.0
    assert levels["profit_retention_pct"] == 55.0
    assert levels["protected_gain_pct"] == 2.2


def test_paper_learning_recovery_is_wired_into_runtime() -> None:
    trading = (ROOT / "trading_engine.py").read_text(encoding="utf-8")
    scanner = (ROOT / "scanner_worker.py").read_text(encoding="utf-8")
    learning = (ROOT / "controlled_parameter_learning.py").read_text(encoding="utf-8")
    assert "strict_profit_protection_levels" in trading
    assert "select_replacement_position" in scanner
    assert "Replacement exit for" in scanner
    assert "_closed_paper_trades" in learning
    assert "Autonomi: daglig Paper + læring" in learning
    assert "PAPER – Paper Trading, eget datasett" in learning
    assert "PRODUKSJON – ordinære Autonomi-handler" in learning
    assert "LÆRING – separate læringshandler og observasjoner" in learning
