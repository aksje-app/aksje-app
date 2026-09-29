from __future__ import annotations

from pathlib import Path

from app_version import APP_VERSION, PREVIOUS_APP_VERSION
from super_portfolio import default_state, portfolio_value_update

ROOT = Path(__file__).resolve().parents[1]


def test_portfolio_value_update_chain_links_previous_holdings_and_cash():
    previous = {
        "AAA": {"target_weight_pct": 60.0, "last_price": 100.0},
        "BBB": {"target_weight_pct": 20.0, "last_price": 50.0},
    }
    result = portfolio_value_update(
        previous,
        {"AAA": 110.0, "BBB": 45.0},
        previous_value=1_000_000.0,
        initial_cash=1_000_000.0,
        transaction_cost=100.0,
    )
    assert result["period_return_pct"] == 4.0
    assert result["portfolio_value"] == 1_039_900.0
    assert result["portfolio_return_pct"] == 3.99
    assert result["transaction_cost"] == 100.0


def test_default_state_starts_at_one_million_theoretical_nav():
    state = default_state()
    assert state["initial_cash"] == 1_000_000.0
    assert state["portfolio_value"] == 1_000_000.0
    assert state["portfolio_return_pct"] == 0.0
    assert state["portfolio_tracking_started_at"]


def test_super_portfolio_page_exposes_total_position_history_and_report_controls():
    source = (ROOT / "pages" / "super_portfolio.py").read_text(encoding="utf-8")
    for required in (
        'Teoretisk verdi',
        'Siden NAV-start',
        'Superporteføljen – utvikling',
        'Utvikling per aksje',
        'Teoretisk verdi NOK',
        'P/L NOK',
        'Åpne / del',
        'Print PDF',
        'Del → Skriv ut',
    ):
        assert required in source


def test_pdf_includes_true_theoretical_nav_summary():
    source = (ROOT / "super_portfolio.py").read_text(encoding="utf-8")
    assert 'Teoretisk verdi: NOK' in source
    assert 'Avkastning siden NAV-sporing' in source
    assert '"portfolio_value": performance["portfolio_value"]' in source
    assert '"portfolio_return_pct": performance["portfolio_return_pct"]' in source


def test_rc16_33p_nav_contract_remains_present():
    state = default_state()
    assert "portfolio_value" in state
    assert "portfolio_return_pct" in state
