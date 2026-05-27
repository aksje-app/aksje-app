from pathlib import Path


def _rules():
    return {
        "stop_loss_pct": 2.5,
        "take_profit_pct": 10.0,
        "trailing_stop_pct": 6.0,
        "rsi_exit_level": 72,
        "rsi_must_fall": True,
        "max_open_positions": 5,
        "max_trades_per_day": 3,
        "min_buy_confidence": 60,
        "position_size_pct": 10.0,
    }


def _position(ticker, entry=100.0, last=100.0, high=None):
    return {
        "ticker": ticker,
        "shares": 10.0,
        "entry_price": entry,
        "avg_price": entry,
        "last_price": last,
        "highest_price": high if high is not None else last,
        "confidence": 88,
        "reason": "test",
        "asset_type": "Aksje",
        "country": "Norge",
        "market": "Norge",
        "sector": "Energy",
        "industry": "Energy",
    }


def _patch_trading_io(monkeypatch, portfolio):
    import trading_engine as te

    def fake_add_trade(p, trade):
        trade["time"] = "test-time"
        p.setdefault("trades", []).insert(0, trade)

    monkeypatch.setattr(te, "load_rules", _rules)
    monkeypatch.setattr(te, "load_portfolio", lambda: portfolio)
    monkeypatch.setattr(te, "save_portfolio", lambda p: False)
    monkeypatch.setattr(te, "add_trade", fake_add_trade)
    monkeypatch.setattr(te, "notify_executed_trade", lambda *args, **kwargs: True)
    monkeypatch.setattr(te, "audit_state_transition", lambda *args, **kwargs: {})
    monkeypatch.setattr(te, "build_paper_state_snapshot", lambda *args, **kwargs: {})
    monkeypatch.setattr(
        te,
        "resolve_trade_security_context",
        lambda ticker, item=None: {
            "country": "Brasil" if str(ticker).endswith(".SA") else "Norge",
            "market": "Brasil" if str(ticker).endswith(".SA") else "Norge",
            "sector": "Energy",
            "industry": "Energy",
            "asset_type": "Aksje",
        },
    )
    return te


def test_auto_trade_stop_loss_overrides_existing_buy_signal(monkeypatch):
    portfolio = {
        "cash": 0.0,
        "positions": {"PRIO3.SA": _position("PRIO3.SA", entry=69.37, last=69.37, high=69.37)},
        "trades": [],
    }
    te = _patch_trading_io(monkeypatch, portfolio)

    traded, msg = te.auto_trade("PRIO3.SA", 64.5, "BUY", confidence=88, rsi=50, prev_rsi=51)

    assert traded is True
    assert "PAPER-SALG" in msg
    assert "PRIO3.SA" not in portfolio["positions"]
    trade = portfolio["trades"][0]
    assert trade["rule_used"] == "Stop-loss"
    assert trade["rule_limit"] == "-2.50%"
    assert trade["country"] == "Brasil"
    assert "Solgt fordi tapet" in trade["trade_explanation"]


def test_auto_trade_rsi_exit_uses_configured_level_and_requires_fall(monkeypatch):
    portfolio = {
        "cash": 0.0,
        "positions": {"NHY.OL": _position("NHY.OL", entry=100.0, last=103.0, high=103.0)},
        "trades": [],
    }
    te = _patch_trading_io(monkeypatch, portfolio)

    traded, msg = te.auto_trade("NHY.OL", 103.0, "HOLD", confidence=87, rsi=77.3, prev_rsi=None)

    assert traded is False
    assert msg == "HOLD NHY.OL"
    assert "NHY.OL" in portfolio["positions"]
    assert portfolio["trades"] == []

    traded, msg = te.auto_trade("NHY.OL", 103.0, "HOLD", confidence=87, rsi=77.3, prev_rsi=80.0)

    assert traded is True
    trade = portfolio["trades"][0]
    assert trade["rule_used"] == "RSI exit"
    assert trade["rule_limit"] == "72.0"
    assert trade["measured_value"] == "77.3"
    assert "RSI var 77.3" in trade["trade_explanation"]


def test_scanner_checks_existing_position_before_direct_buy():
    text = Path("scanner_worker.py").read_text(encoding="utf-8", errors="ignore")

    assert "has_existing_position" in text
    assert text.index("has_existing_position") < text.index('if "BUY" in signal_text')
    assert "Auto risk check" in text


def test_control_center_shows_datakilder_as_visible_start():
    text = Path("workspace_layout.py").read_text(encoding="utf-8", errors="ignore")

    assert "_render_pipeline_quick_start_v1863bx" in text
    assert '"Start her: 1. Dataunderlag"' in text
    assert '"Marked og signaler": _matching_panel_labels("dataunderlag", "datakilder", "datagrunnlag", "analyseflyt", "test 1"' in text

