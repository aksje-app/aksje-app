
from datetime import datetime

from paper_store import (
    init_store, get_cash, set_cash, get_positions, get_position, upsert_position,
    delete_position, add_trade, get_trades, trades_today, inc_trade_count, reset_all
)
from trading_settings import load_rules, calc_stop_take, should_sell


def load_portfolio():
    init_store()
    return {
        "cash": get_cash(),
        "positions": get_positions(),
        "trades": get_trades(200),
        "daily_trade_count": {"today": trades_today()},
    }


def save_portfolio(portfolio):
    return None


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
    return trades_today() < int(rules["max_trades_per_day"])


def has_room_for_position(rules=None):
    rules = rules or load_rules()
    return len(get_positions()) < int(rules["max_open_positions"])


def position_amount(rules=None):
    rules = rules or load_rules()
    portfolio = load_portfolio()
    value = portfolio_value(portfolio)
    pct = float(rules["position_size_pct"]) / 100
    amount = value * pct
    cash = float(portfolio.get("cash", 0))
    return round(min(amount, cash), 2)


def update_last_price(ticker, price):
    pos = get_position(ticker)
    if not pos:
        return
    price = float(price)
    rules = load_rules()
    sl, tp = calc_stop_take(pos.get("avg_price", price), rules)
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
    if not can_trade_today(rules):
        return False, f"Maks {rules['max_trades_per_day']} trades per dag nådd"
    if get_position(ticker):
        return False, "Har allerede posisjon"
    if not has_room_for_position(rules):
        return False, f"Maks {rules['max_open_positions']} åpne posisjoner nådd"

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
        "decision": decision,
        "reason": "Auto BUY",
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
        return False, f"Maks {rules['max_trades_per_day']} trades per dag nådd"

    shares = float(pos.get("shares", 0))
    amount = shares * price
    entry_price = float(pos.get("avg_price", price))
    pnl_pct = ((price - entry_price) / entry_price * 100) if entry_price else 0

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
    """
    Full auto paper trading:
    - Kjøper når BUY-regler er oppfylt
    - Selger når SELL/stop-loss/take-profit/RSI-exit trigger
    """
    from trading_settings import should_buy, should_sell

    rules = load_rules()
    pos = get_position(ticker)

    if pos:
        update_last_price(ticker, price)
        pos = get_position(ticker)
        sell_ok, reason = should_sell(decision, pos, price, rsi, prev_rsi, rules)
        if sell_ok:
            return paper_sell(ticker, price, decision, reason=reason)
        return False, "HOLD posisjon"

    if should_buy(decision, rsi, rules):
        return paper_buy(ticker, price, decision)

    return False, "Ingen trade"


def reset_portfolio():
    rules = load_rules()
    reset_all(float(rules["start_cash"]))
    return load_portfolio()


def performance_stats(portfolio=None, latest_prices=None):
    rules = load_rules()
    portfolio = portfolio or load_portfolio()
    latest_prices = latest_prices or {}
    start_cash = float(rules["start_cash"])
    total_value = portfolio_value(portfolio, latest_prices)
    total_return = ((total_value - start_cash) / start_cash * 100) if start_cash else 0
    sells = [t for t in portfolio.get("trades", []) if t.get("type") == "SELL" and t.get("pnl_pct") is not None]
    wins = [t for t in sells if float(t.get("pnl_pct", 0)) > 0]
    losses = [t for t in sells if float(t.get("pnl_pct", 0)) <= 0]
    win_rate = (len(wins) / len(sells) * 100) if sells else 0
    avg_win = sum(float(t["pnl_pct"]) for t in wins) / len(wins) if wins else 0
    avg_loss = sum(float(t["pnl_pct"]) for t in losses) / len(losses) if losses else 0
    return {
        "start_cash": round(start_cash, 2),
        "total_value": round(total_value, 2),
        "total_return_pct": round(total_return, 2),
        "closed_trades": len(sells),
        "open_positions": len(portfolio.get("positions", {})),
        "win_rate": round(win_rate, 1),
        "avg_win": round(avg_win, 2),
        "avg_loss": round(avg_loss, 2),
        "trades_today": trades_today(),
        "max_trades_per_day": int(rules["max_trades_per_day"]),
    }
