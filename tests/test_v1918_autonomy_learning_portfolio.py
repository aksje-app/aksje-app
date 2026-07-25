from autonomi_core.runtime.orchestrator import execute_market_mission
from autonomous_portfolio import (
    AutonomousParameters,
    default_portfolio,
    load_equity_history,
    portfolio_status_summary,
    run_autonomous_cycle,
    save_parameters,
    _write,
    PORTFOLIO_PATH,
    TRADES_PATH,
    DECISIONS_PATH,
    EQUITY_HISTORY_PATH,
)


def _reset_active():
    params = save_parameters(AutonomousParameters(
        initial_cash=100000,
        minimum_investment_score=90,
        minimum_data_quality=90,
        maximum_risk_score=30,
        maximum_position_pct=5,
        maximum_sector_pct=50,
        maximum_open_positions=10,
        reserve_cash_pct=0,
        enable_learning_probe_buys=True,
        learning_probe_minimum_score=70,
        learning_probe_max_buys=2,
        notify_trades=False,
        notify_risk_events=False,
    ))
    portfolio = default_portfolio(params)
    portfolio["status"] = "ACTIVE"
    portfolio["pause_reason"] = ""
    _write(PORTFOLIO_PATH, portfolio)
    _write(TRADES_PATH, [])
    _write(DECISIONS_PATH, [])
    _write(EQUITY_HISTORY_PATH, [])


def test_learning_probe_buys_when_ordinary_gates_block_all_candidates():
    _reset_active()
    candidates = [
        {"ticker": "AAA", "investment_score": 74, "data_quality": 100, "risk_score": 40, "price": 100, "sector": "Finans", "strategy_match": "Momentum", "portfolio_action": "REVIEW"},
        {"ticker": "BBB", "investment_score": 72, "data_quality": 100, "risk_score": 40, "price": 50, "sector": "Industri", "strategy_match": "Vekst", "portfolio_action": "REVIEW"},
    ]
    result = run_autonomous_cycle(candidates, "TEST-V1918")
    buys = [t for t in result["trades"] if t["action"] == "BUY"]
    assert len(buys) == 2
    assert all(t.get("learning_probe") for t in buys)
    assert result["portfolio"]["positions"]["AAA"].get("origin") == "AUTONOMY_LEARNING_PROBE"
    assert load_equity_history(10)


def test_runtime_forwards_observed_candidates_for_learning_when_decision_gate_blocks_all():
    _reset_active()
    run = {
        "run_id": "MI-TEST-V1918",
        "markets": ["USA", "Norge"],
        "candidates": [
            {"ticker": "CCC", "investment_score": 75, "data_quality": 95, "risk_score": 40, "price": 80, "valid_for_decision": False, "portfolio_action": "REVIEW"},
        ],
        "proposals": [],
        "timezone_name": "Europe/Oslo",
    }
    result = execute_market_mission(run, trigger="TEST", run_autonomous=True, run_learning=False, require_active_portfolio=True)
    market = next(s for s in result["stages"] if s["name"] == "MARKET_SCAN")
    auto = next(s for s in result["stages"] if s["name"] == "AUTONOMOUS_PORTFOLIO")
    assert market["detail"]["candidates"] == 1
    assert market["detail"]["handoff_input"]["learning_probe_mode"] is True
    assert auto["detail"]["learning_buys"] >= 1


def test_status_panel_exposes_expected_autonomy_state():
    summary = portfolio_status_summary({
        "stages": [
            {"name": "MARKET_SCAN", "detail": {"candidates": 0}},
            {"name": "AUTONOMOUS_PORTFOLIO", "status": "SKIPPED", "detail": {"reason": "Ingen kandidater fra skanning"}},
        ]
    })
    assert summary["Ekte handel"] == "Deaktivert"
    assert summary["Paper trading"] == "Aktiv"
    assert summary["Kandidater mottatt"] == 0
    assert "Ingen kandidater" in summary["Årsak til ingen kjøp"]
