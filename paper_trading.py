
import os
from datetime import datetime

from paper_store import (
    init_store, get_cash, set_cash, get_positions, get_position, upsert_position,
    delete_position, add_trade, get_trades, trades_today, inc_trade_count, reset_all
)

DEFAULT_START_CASH = float(os.getenv("PAPER_START_CASH", "100000"))
DEFAULT_POSITION_SIZE = float(os.getenv("PAPER_POSITION_SIZE", "10000"))
STOP_LOSS_PCT = float(os.getenv("PAPER_STOP_LOSS_PCT", "0.06"))
TRAILING_STOP_PCT = float(os.getenv("PAPER_TRAILING_STOP_PCT", "0.08"))
MAX_TRADES_PER_DAY = int(os.getenv("MAX_TRADES_PER_DAY", "3"))

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

def can_trade_today():
    return trades_today() < MAX_TRADES_PER_DAY

def portfolio_value(portfolio=None, latest_prices=None):
    latest_prices = latest_prices or {}
    portfolio = portfolio or load_portfolio()
    value = float(portfolio.get("cash", 0))
    for ticker, pos in portfolio.get("positions", {}).items():
        shares = float(pos.get("shares", 0))
        price = latest_prices.get(ticker, pos.get("last_price", pos.get("avg_price", 0)))
        value += shares * float(price or 0)
    return round(value, 2)

def update_last_price(ticker, price):
    pos = get_position(ticker)
    if not pos:
        return
    price = float(price)
    pos["last_price"] = price
    pos["highest_price"] = max(float(pos.get("highest_price", price)), price)
    upsert_position(ticker, pos)

def should_stop_loss(position, current_price):
    entry = float(position.get("avg_price", 0))
    return bool(entry > 0 and float(current_price) <= entry * (1 - STOP_LOSS_PCT))

def should_trailing_stop(position, current_price):
    highest = float(position.get("highest_price", position.get("avg_price", 0)))
    return bool(highest > 0 and float(current_price) <= highest * (1 - TRAILING_STOP_PCT))

def paper_buy(ticker, price, decision, amount=None):
    amount = float(amount or DEFAULT_POSITION_SIZE)
    price = float(price)
    if price <= 0:
        return False, "Ugyldig pris"
    if not can_trade_today():
        return False, f"Maks {MAX_TRADES_PER_DAY} trades per dag nådd"
    if get_position(ticker):
        return False, "Har allerede posisjon"
    cash = get_cash()
    if cash < amount:
        amount = cash
    if amount <= 0:
        return False, "Ingen cash tilgjengelig"
    shares = amount / price
    pos = {
        "shares": shares,
        "avg_price": price,
        "last_price": price,
        "highest_price": price,
        "stop_loss": round(price * (1 - STOP_LOSS_PCT), 4),
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
    })
    inc_trade_count()
    return True, f"Paper BUY {ticker}"

def paper_sell(ticker, price, decision, reason="SELL signal"):
    price = float(price)
    pos = get_position(ticker)
    if not pos:
        return False, "Ingen posisjon å selge"
    if not can_trade_today():
        return False, f"Maks {MAX_TRADES_PER_DAY} trades per dag nådd"
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

def apply_risk_exits(ticker, price):
    pos = get_position(ticker)
    if not pos:
        return False, "Ingen posisjon"
    price = float(price)
    pos["last_price"] = price
    pos["highest_price"] = max(float(pos.get("highest_price", price)), price)
    upsert_position(ticker, pos)
    if should_stop_loss(pos, price):
        return paper_sell(ticker, price, {"decision": "STOP LOSS"}, reason="Stop-loss")
    if should_trailing_stop(pos, price):
        return paper_sell(ticker, price, {"decision": "TRAILING STOP"}, reason="Trailing stop")
    return False, "Ingen risk-exit"

def reset_portfolio():
    reset_all(DEFAULT_START_CASH)
    return load_portfolio()

def performance_stats(portfolio=None, latest_prices=None):
    portfolio = portfolio or load_portfolio()
    latest_prices = latest_prices or {}
    start_cash = DEFAULT_START_CASH
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
        "max_trades_per_day": MAX_TRADES_PER_DAY,
    }
