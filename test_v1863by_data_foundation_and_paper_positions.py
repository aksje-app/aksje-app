from pathlib import Path

from paper_trading_valuation import paper_position_rows, paper_trade_rows


ROOT = Path(__file__).resolve().parent


def test_version_bumped_to_datakilder_cockpit():
    version = (ROOT / "app_version.py").read_text(encoding="utf-8")
    assert 'APP_VERSION = "v18.6.4e"' in version
    assert "Dynamic Slider Guard" in version


def test_test1_has_real_data_foundation_workspace_not_dead_top_start():
    app = (ROOT / "app.py").read_text(encoding="utf-8")
    assert '_render_pipeline_stage_bar_v1863bw("data_foundation", show_actions=False)' in app
    assert "_render_data_foundation_workspace_v1863by(status_rows)" in app
    assert "_render_data_foundation_approval_v1863by(status_rows)" in app
    assert "Importer Finansavisen-filer" in app
    assert "Rediger Aktoerregister" in app
    assert "Importer Oljefond/NBIM" in app
    assert "Mottatt fra forrige test" in app
    assert "Kontrollrapport klar" in app
    assert "Start her: godkjenn datagrunnlag" not in app


def test_paper_positions_can_fill_trade_fields_from_position_cards():
    app = (ROOT / "app.py").read_text(encoding="utf-8")
    assert "def _select_paper_position_for_trade_v1863by" in app
    assert "paper_stock_sell_symbol_v1863y" in app
    assert "paper_stock_sell_price_v1863y" in app
    assert "Velg for salg" in app
    assert "Velg for kjop/ok" in app
    assert "Land <b>" in app
    assert "Marked <b>" in app
    assert "Sektor <b>" in app
    assert "Bransje <b>" in app


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




