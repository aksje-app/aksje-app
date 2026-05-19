from paper_trading_valuation import normalize_paper_portfolio, paper_position_rows, paper_trade_rows
from trading_engine import paper_liquidity_snapshot, portfolio_value


def test_position_uses_entry_price_when_avg_price_is_missing():
    portfolio = {
        "cash": 10000,
        "positions": {
            "JNJ": {"ticker": "JNJ", "shares": 100, "entry_price": 200, "last_price": 230},
        },
        "trades": [],
    }
    normalized = normalize_paper_portfolio(portfolio)
    pos = normalized["positions"]["JNJ"]
    assert pos["avg_price"] == 200
    assert pos["market_value"] == 23000
    assert round(pos["pnl_pct"], 2) == 15.0

    rows = paper_position_rows(portfolio)
    assert rows[0]["avg_price"] == 200
    assert rows[0]["value"] == 23000
    assert rows[0]["pnl_pct"] == 15.0


def test_liquidity_and_portfolio_value_use_normalized_entry_and_last_price():
    portfolio = {
        "cash": 10000,
        "positions": {
            "MRK": {"ticker": "MRK", "shares": 10, "entry_price": 100, "last_price": 110},
        },
        "trades": [],
    }
    snap = paper_liquidity_snapshot(portfolio)
    assert snap["positions_value"] == 1100
    assert snap["unrealized_pnl"] == 100
    assert portfolio_value(portfolio) == 11100


def test_trade_log_labels_paper_actions():
    rows = paper_trade_rows([
        {"type": "BUY", "ticker": "NVDA", "reason": "AUTO BUY via Cron/Kjøp nå"},
        {"type": "SELL", "ticker": "NVDA", "reason": "Stop loss"},
    ])
    assert rows[0]["type"] == "PAPER-KJØP"
    assert rows[0]["reason"].startswith("PAPER-KJØP")
    assert rows[1]["type"] == "PAPER-SALG"
