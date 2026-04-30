
from datetime import datetime
from paper_store import (
    init_store, get_cash, set_cash, get_positions, get_position, upsert_position,
    delete_position, add_trade, get_trades, trades_today, inc_trade_count, reset_all
)
from trading_settings import load_rules, calc_stop_take, should_buy, should_sell

try:
    _r = load_rules()
except Exception:
    _r = {}

STOP_LOSS_PCT = float(_r.get("stop_loss_pct", 7.0)) / 100
TRAILING_STOP_PCT = float(_r.get("trailing_stop_pct", 8.0)) / 100
MAX_TRADES_PER_DAY = int(_r.get("max_trades_per_day", 3))


def load_portfolio():
    init_store()
    return {
        "cash": get_cash(),
        "positions": get_positions(),
        "trades": get_trades(300),
        "daily_trade_count": {"today": trades_today()},
    }


def portfolio_value(portfolio=None, latest_prices=None):
    latest_prices = latest_prices or {}
    portfolio = portfolio or load_portfolio()
    value = float(portfolio.get("cash", 0))
    for ticker, pos in portfolio.get("positions", {}).items():
        shares = float(pos.get("shares", 0))
        price = latest_prices.get(ticker, pos.get("last_price", pos.get("avg_price", 0)))
        value += shares * float(price or 0)
    return round(value, 2)


def can_trade_today(rules=None):
    rules = rules or load_rules()
    return trades_today() < int(rules.get("max_trades_per_day", 3))


def has_room_for_position(rules=None):
    rules = rules or load_rules()
    return len(get_positions()) < int(rules.get("max_open_positions", 5))


def position_amount(rules=None):
    rules = rules or load_rules()
    p = load_portfolio()
    value = portfolio_value(p)
    cash = float(p.get("cash", 0))
    amount = value * float(rules.get("position_size_pct", 10.0)) / 100
    return round(min(amount, cash), 2)


def update_last_price(ticker, price):
    pos = get_position(ticker)
    if not pos:
        return
    price = float(price)
    rules = load_rules()
    sl, tp = calc_stop_take(float(pos.get("avg_price", price)), rules)
    pos["last_price"] = price
    pos["highest_price"] = max(float(pos.get("highest_price", price)), price)
    pos["stop_loss"] = sl
    pos["take_profit"] = tp
    upsert_position(ticker, pos)


def paper_buy(ticker, price, decision, amount=None):
    rules = load_rules()
    price = float(price)

    if price <= 0:
        return False, "Ugyldig pris"
    if get_position(ticker):
        return False, "Har allerede posisjon"
    if not can_trade_today(rules):
        return False, f"Maks {rules.get('max_trades_per_day', 3)} trades per dag nådd"
    if not has_room_for_position(rules):
        return False, f"Maks {rules.get('max_open_positions', 5)} åpne posisjoner nådd"

    amount = float(amount or position_amount(rules))
    cash = get_cash()
    amount = min(amount, cash)
    if amount <= 0:
        return False, "Ingen cash tilgjengelig"

    shares = amount / price
    sl, tp = calc_stop_take(price, rules)

    pos = {
        "shares": shares,
        "avg_price": price,
        "last_price": price,
        "highest_price": price,
        "stop_loss": sl,
        "take_profit": tp,
        "entry_time": datetime.utcnow().isoformat(),
        "entry_signal": decision,
    }

    set_cash(round(cash - amount, 2))
    upsert_position(ticker, pos)

    add_trade({
        "time": datetime.utcnow().isoformat(),
        "type": "BUY",
        "ticker": ticker,
        "price": round(price, 4),
        "shares": round(shares, 6),
        "amount": round(amount, 2),
        "pnl_pct": None,
        "reason": "Auto BUY",
        "decision": decision,
    })
    inc_trade_count()
    return True, f"Paper BUY {ticker}"


def paper_sell(ticker, price, decision, reason="SELL"):
    rules = load_rules()
    price = float(price)
    pos = get_position(ticker)

    if not pos:
        return False, "Ingen posisjon å selge"
    if not can_trade_today(rules):
        return False, f"Maks {rules.get('max_trades_per_day', 3)} trades per dag nådd"

    shares = float(pos.get("shares", 0))
    amount = shares * price
    entry = float(pos.get("avg_price", price))
    pnl_pct = ((price - entry) / entry * 100) if entry else 0

    set_cash(round(get_cash() + amount, 2))

    add_trade({
        "time": datetime.utcnow().isoformat(),
        "type": "SELL",
        "ticker": ticker,
        "price": round(price, 4),
        "shares": round(shares, 6),
        "amount": round(amount, 2),
        "pnl_pct": round(pnl_pct, 2),
        "reason": reason,
        "decision": decision,
    })

    delete_position(ticker)
    inc_trade_count()
    return True, f"Paper SELL {ticker}, PnL {pnl_pct:.2f}%"


def auto_trade(ticker, price, decision, rsi=None, prev_rsi=None):
    pos = get_position(ticker)

    if pos:
        update_last_price(ticker, price)
        pos = get_position(ticker)
        sell_ok, reason = should_sell(decision, pos, price, rsi, prev_rsi, load_rules())
        if sell_ok:
            return paper_sell(ticker, price, decision, reason=reason)
        return False, "HOLD posisjon"

    if should_buy(decision, rsi, load_rules()):
        return paper_buy(ticker, price, decision)

    return False, "Ingen trade"


def apply_risk_exits(ticker, price):
    return auto_trade(ticker, price, {"decision": "HOLD"}, rsi=None)


def reset_portfolio():
    reset_all(float(load_rules().get("start_cash", 100000)))
    return load_portfolio()


def performance_stats(portfolio=None, latest_prices=None):
    rules = load_rules()
    portfolio = portfolio or load_portfolio()
    start_cash = float(rules.get("start_cash", 100000))
    total_value = portfolio_value(portfolio, latest_prices or {})
    total_return = ((total_value - start_cash) / start_cash * 100) if start_cash else 0

    sells = [t for t in portfolio.get("trades", []) if t.get("type") == "SELL" and t.get("pnl_pct") is not None]
    wins = [t for t in sells if float(t.get("pnl_pct", 0)) > 0]
    losses = [t for t in sells if float(t.get("pnl_pct", 0)) <= 0]

    return {
        "start_cash": round(start_cash, 2),
        "total_value": round(total_value, 2),
        "total_return_pct": round(total_return, 2),
        "closed_trades": len(sells),
        "open_positions": len(portfolio.get("positions", {})),
        "win_rate": round(len(wins) / len(sells) * 100, 1) if sells else 0,
        "avg_win": round(sum(float(t["pnl_pct"]) for t in wins) / len(wins), 2) if wins else 0,
        "avg_loss": round(sum(float(t["pnl_pct"]) for t in losses) / len(losses), 2) if losses else 0,
        "trades_today": trades_today(),
        "max_trades_per_day": int(rules.get("max_trades_per_day", 3)),
    }


def save_portfolio(portfolio):
    return None
