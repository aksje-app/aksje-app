from pathlib import Path

from paper_trading_valuation import (
    PAPER_SHARED_COLUMNS,
    paper_position_display_rows,
    paper_position_rows,
    paper_trade_display_rows,
    paper_trade_rows,
)


ROOT = Path(__file__).resolve().parent


def test_version_bumped_to_datakilder_cockpit():
    version = (ROOT / "app_version.py").read_text(encoding="utf-8")
    assert 'APP_VERSION = "v18.6.8"' in version
    assert "Paper Trading og auth-kontroll" in version
    assert "Paper Trading er omdøpt til Paper Trading og kontroll" in version


def test_test1_has_real_data_foundation_workspace_not_dead_top_start():
    app = (ROOT / "app.py").read_text(encoding="utf-8")
    assert "#### Kilder og import" in app
    assert "_render_data_foundation_workspace_v1863by([])" in app
    assert "source_options =" in app and "Folketrygdfondet" in app and "Akt" in app
    assert "Dette er eneste synlige importsted" in app
    assert "Mottatt fra forrige test" not in app
    assert "Kontrollrapport klar" not in app
    assert "Start her: godkjenn datagrunnlag" not in app


def test_paper_positions_can_fill_trade_fields_from_position_cards():
    app = (ROOT / "app.py").read_text(encoding="utf-8")
    assert "def _select_paper_position_for_trade_v1863by" in app
    assert "paper_stock_sell_symbol_v1863y" in app
    assert "paper_stock_sell_price_v1863y" in app
    assert '"Selg"' in app
    assert '"Øk"' in app
    assert "Velg for salg" not in app
    assert "paper_position_select_buy_v1863by" in app
    assert "paper-position-hint" in app
    assert "Land <b>" in app
    assert "Marked <b>" in app
    assert "Sektor <b>" in app
    assert "Bransje <b>" in app


def test_paper_trading_and_control_are_unified_in_one_visible_panel():
    app = (ROOT / "app.py").read_text(encoding="utf-8")
    assert "🧪 Paper Trading og kontroll" in app
    assert "render_paper_trading_dashboard()" in app
    assert "Innkommende paper-hypoteser" in app
    assert "Kandidater sendt til Paper Trading:" not in app
    assert 'panels.insert(3, ("🧭 Paper-portefølje kontroll"' not in app


def test_portfolio_analysis_positions_render_as_readable_table():
    app = (ROOT / "app.py").read_text(encoding="utf-8")
    assert "def _portfolio_position_table_rows_v1864h" in app
    assert '"Ticker / selskap"' in app
    assert '"Sektor"' in app
    assert '"Marked"' in app
    assert "resolve_security_metadata(symbol, row)" in app
    assert "infer_security_listing(symbol, meta)" in app
    assert "st.dataframe(pd.DataFrame(_portfolio_position_table_rows_v1864h(rows))" in app


def test_paper_position_rows_backfill_market_context_for_old_positions():
    rows = paper_position_rows(
        {
            "positions": {
                "PRIO3.SA": {"shares": 3, "avg_price": 10, "last_price": 12},
                "DNB.OL": {"shares": 2, "avg_price": 100, "last_price": 110},
            }
        },
        {},
    )
    by_ticker = {row["ticker"]: row for row in rows}
    assert by_ticker["PRIO3.SA"]["land"] == "Brasil"
    assert by_ticker["PRIO3.SA"]["marked"] == "Brasil"
    assert by_ticker["DNB.OL"]["land"] == "Norge"
    assert by_ticker["DNB.OL"]["marked"] == "Norge"


def test_paper_trade_rows_backfill_market_context_for_old_trades():
    rows = paper_trade_rows(
        [
            {"type": "BUY", "ticker": "DNB.OL", "price": 286.5},
            {"type": "SELL", "ticker": "NVDA", "price": 220.0},
        ],
        limit=10,
    )
    by_ticker = {row["ticker"]: row for row in rows}
    assert by_ticker["DNB.OL"]["land"] == "Norge"
    assert by_ticker["DNB.OL"]["marked"] == "Norge"
    assert by_ticker["NVDA"]["land"] == "USA"
    assert by_ticker["NVDA"]["marked"] == "USA"


def test_paper_display_rows_share_common_contract_for_holdings_and_trades():
    portfolio = {
        "cash": 10000,
        "positions": {
            "DNB.OL": {
                "shares": 2,
                "avg_price": 100,
                "last_price": 110,
                "confidence": 80,
                "reason": "AI Kandidattest",
            }
        },
        "trades": [
            {
                "time": "2026-06-02T10:00:00",
                "type": "BUY",
                "ticker": "DNB.OL",
                "price": 100,
                "shares": 2,
                "amount": 200,
            },
        ],
    }
    position_rows = paper_position_display_rows(portfolio, total_value=10220)
    trade_rows = paper_trade_display_rows(portfolio["trades"], limit=10)
    assert position_rows and trade_rows
    assert list(position_rows[0].keys()) == PAPER_SHARED_COLUMNS
    assert list(trade_rows[0].keys()) == PAPER_SHARED_COLUMNS
    assert position_rows[0]["Status"] == "Åpen"
    assert trade_rows[0]["Status"] == "Historisk"








