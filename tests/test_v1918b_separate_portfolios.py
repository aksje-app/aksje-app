from pathlib import Path


def test_source_exposes_two_distinct_portfolio_views_and_routes():
    root = Path(__file__).resolve().parents[1]
    app = (root / "app.py").read_text(encoding="utf-8")
    overview = (root / "autonomy_overview.py").read_text(encoding="utf-8")
    portfolio = (root / "autonomous_portfolio.py").read_text(encoding="utf-8")
    assert '"autonomous_portfolio": "Autonom portefølje"' in app
    assert '"learning_portfolio": "Læringsportefølje"' in app
    assert 'Åpne autonom portefølje' in overview
    assert 'Vis læringsportefølje' in overview
    assert 'def render_learning_portfolio()' in portfolio
    assert 'Separate skyggeposisjoner' in portfolio


def test_learning_positions_do_not_modify_ordinary_cash_or_holdings():
    from autonomous_portfolio import (
        AutonomousParameters, default_portfolio, default_learning_portfolio,
        run_autonomous_cycle, save_parameters, _write,
        PORTFOLIO_PATH, LEARNING_PORTFOLIO_PATH, TRADES_PATH, DECISIONS_PATH,
        LEARNING_TRADES_PATH, LEARNING_DECISIONS_PATH, EQUITY_HISTORY_PATH,
        LEARNING_EQUITY_HISTORY_PATH,
    )
    params = save_parameters(AutonomousParameters(
        initial_cash=100000, minimum_investment_score=90, minimum_data_quality=90,
        maximum_risk_score=30, reserve_cash_pct=0, maximum_sector_pct=50,
        enable_learning_probe_buys=True, learning_probe_minimum_score=70,
        learning_probe_max_buys=2, learning_probe_notional_value=2500,
        notify_trades=False, notify_risk_events=False,
    ))
    primary = default_portfolio(params); primary["status"] = "ACTIVE"; primary["pause_reason"] = ""
    _write(PORTFOLIO_PATH, primary); _write(LEARNING_PORTFOLIO_PATH, default_learning_portfolio(params))
    for path in (TRADES_PATH, DECISIONS_PATH, LEARNING_TRADES_PATH, LEARNING_DECISIONS_PATH, EQUITY_HISTORY_PATH, LEARNING_EQUITY_HISTORY_PATH):
        _write(path, [])
    result = run_autonomous_cycle([
        {"ticker":"AAA","investment_score":74,"data_quality":100,"risk_score":40,"price":100,"sector":"Finans"},
        {"ticker":"BBB","investment_score":72,"data_quality":100,"risk_score":40,"price":50,"sector":"Industri"},
    ], "TEST-V1918B")
    assert result["portfolio"]["positions"] == {}
    assert result["portfolio"]["cash"] == 100000
    assert set(result["learning_portfolio"]["positions"]) == {"AAA", "BBB"}
    assert result["portfolio_trades"] == []
    assert len(result["learning_trades"]) == 2


def test_app_version_is_v19019():
    from app_version import APP_VERSION
    assert APP_VERSION == "v19.0.19"
