import trading_engine
from app_version import get_app_version


def _fake_portfolio():
    return {"cash": 10_000.0, "positions": {}, "trades": [], "fund_savings_plans": []}


def test_paper_buy_instrument_amount_based_and_accumulates(monkeypatch):
    portfolio = _fake_portfolio()

    def fake_load():
        return portfolio

    def fake_save(p):
        snapshot = dict(p)
        portfolio.clear()
        portfolio.update(snapshot)

    def fake_add_trade(p, trade):
        trade = dict(trade)
        trade["time"] = "test"
        p.setdefault("trades", []).insert(0, trade)
        fake_save(p)

    monkeypatch.setattr(trading_engine, "load_portfolio", fake_load)
    monkeypatch.setattr(trading_engine, "save_portfolio", fake_save)
    monkeypatch.setattr(trading_engine, "add_trade", fake_add_trade)
    monkeypatch.setattr(trading_engine, "notify_executed_trade", lambda *a, **k: True)

    ok, msg = trading_engine.paper_buy_instrument("voo", price=100, amount=1_000, asset_type="ETF", currency="USD")
    assert ok, msg
    assert portfolio["cash"] == 9_000.0
    assert portfolio["positions"]["VOO"]["asset_type"] == "ETF"
    assert round(portfolio["positions"]["VOO"]["shares"], 4) == 10.0
    assert portfolio["positions"]["VOO"]["units_label"] == "units"

    ok, msg = trading_engine.paper_buy_instrument("VOO", price=200, amount=1_000, asset_type="ETF", currency="USD")
    assert ok, msg
    pos = portfolio["positions"]["VOO"]
    assert round(pos["shares"], 4) == 15.0
    assert round(pos["avg_price"], 4) == round(2_000 / 15, 4)
    assert portfolio["trades"][0]["order_kind"] == "amount_buy"
    assert portfolio["trades"][0]["asset_type"] == "ETF"


def test_paper_sell_instrument_partial_and_portfolio_value(monkeypatch):
    portfolio = {
        "cash": 0.0,
        "positions": {
            "KLPX": {
                "ticker": "KLPX",
                "shares": 100.0,
                "entry_price": 100.0,
                "avg_price": 100.0,
                "last_price": 110.0,
                "asset_type": "Indeksfond",
                "units_label": "andeler",
                "currency": "NOK",
            }
        },
        "trades": [],
        "fund_savings_plans": [],
    }

    def fake_load():
        return portfolio

    def fake_save(p):
        snapshot = dict(p)
        portfolio.clear()
        portfolio.update(snapshot)

    def fake_add_trade(p, trade):
        trade = dict(trade)
        trade["time"] = "test"
        p.setdefault("trades", []).insert(0, trade)
        fake_save(p)

    monkeypatch.setattr(trading_engine, "load_portfolio", fake_load)
    monkeypatch.setattr(trading_engine, "save_portfolio", fake_save)
    monkeypatch.setattr(trading_engine, "add_trade", fake_add_trade)
    monkeypatch.setattr(trading_engine, "notify_executed_trade", lambda *a, **k: True)

    assert trading_engine.portfolio_value(portfolio) == 11_000.0
    ok, msg = trading_engine.paper_sell_instrument("KLPX", price=110, sell_amount=5_500, currency="NOK")
    assert ok, msg
    assert round(portfolio["positions"]["KLPX"]["shares"], 4) == 50.0
    assert portfolio["cash"] == 5_500.0
    assert portfolio["trades"][0]["order_kind"] == "amount_sell"
    assert portfolio["trades"][0]["asset_type"] == "Indeksfond"


def test_version_is_18545():
    assert get_app_version() == "v18.5.74"
