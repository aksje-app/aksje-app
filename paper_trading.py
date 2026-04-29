import json
import os
from datetime import datetime, date
from pathlib import Path

PORTFOLIO_FILE = Path(os.getenv("PAPER_PORTFOLIO_FILE", "paper_portfolio.json"))

DEFAULT_START_CASH = float(os.getenv("PAPER_START_CASH", "100000"))
DEFAULT_POSITION_SIZE = float(os.getenv("PAPER_POSITION_SIZE", "10000"))
STOP_LOSS_PCT = float(os.getenv("PAPER_STOP_LOSS_PCT", "0.06"))
TRAILING_STOP_PCT = float(os.getenv("PAPER_TRAILING_STOP_PCT", "0.08"))
MAX_TRADES_PER_DAY = int(os.getenv("MAX_TRADES_PER_DAY", "3"))


def _today():
    return date.today().isoformat()


def _empty_portfolio():
    return {
        "cash": DEFAULT_START_CASH,
        "positions": {},
        "trades": [],
        "daily_trade_count": {},
        "created_at": datetime.utcnow().isoformat(),
        "updated_at": datetime.utcnow().isoformat(),
    }


def load_portfolio():
    if not PORTFOLIO_FILE.exists():
        portfolio = _empty_portfolio()
        save_portfolio(portfolio)
        return portfolio

    try:
        with open(PORTFOLIO_FILE, "r", encoding="utf-8") as f:
            portfolio = json.load(f)
            portfolio.setdefault("daily_trade_count", {})
            portfolio.setdefault("positions", {})
            portfolio.setdefault("trades", [])
            return portfolio
    except Exception:
        portfolio = _empty_portfolio()
        save_portfolio(portfolio)
        return portfolio


def save_portfolio(portfolio):
    portfolio["updated_at"] = datetime.utcnow().isoformat()
    with open(PORTFOLIO_FILE, "w", encoding="utf-8") as f:
        json.dump(portfolio, f, indent=2, ensure_ascii=False, default=str)


def trades_today(portfolio):
    return int(portfolio.setdefault("daily_trade_count", {}).get(_today(), 0))


def can_trade_today(portfolio):
    return trades_today(portfolio) < MAX_TRADES_PER_DAY


def _inc_trade_count(portfolio):
    today = _today()
    portfolio.setdefault("daily_trade_count", {})
    portfolio["daily_trade_count"][today] = portfolio["daily_trade_count"].get(today, 0) + 1


def portfolio_value(portfolio, latest_prices=None):
    latest_prices = latest_prices or {}
    value = float(portfolio.get("cash", 0))

    for ticker, pos in portfolio.get("positions", {}).items():
        shares = float(pos.get("shares", 0))
        price = latest_prices.get(ticker, pos.get("last_price", pos.get("avg_price", 0)))
        value += shares * float(price or 0)

    return round(value, 2)


def update_last_price(ticker, price):
    portfolio = load_portfolio()
    if ticker in portfolio.get("positions", {}):
        pos = portfolio["positions"][ticker]
        pos["last_price"] = float(price)
        pos["highest_price"] = max(float(pos.get("highest_price", price)), float(price))
        save_portfolio(portfolio)


def should_stop_loss(position, current_price):
    entry = float(position.get("avg_price", 0))
    if entry <= 0:
        return False
    return float(current_price) <= entry * (1 - STOP_LOSS_PCT)


def should_trailing_stop(position, current_price):
    highest = float(position.get("highest_price", position.get("avg_price", 0)))
    if highest <= 0:
        return False
    return float(current_price) <= highest * (1 - TRAILING_STOP_PCT)


def paper_buy(ticker, price, decision, amount=None):
    amount = float(amount or DEFAULT_POSITION_SIZE)
    price = float(price)

    if price <= 0:
        return False, "Ugyldig pris"

    portfolio = load_portfolio()

    if not can_trade_today(portfolio):
        return False, f"Maks {MAX_TRADES_PER_DAY} trades per dag nådd"

    if ticker in portfolio.get("positions", {}):
        return False, "Har allerede posisjon"

    cash = float(portfolio.get("cash", 0))
    if cash < amount:
        amount = cash

    if amount <= 0:
        return False, "Ingen cash tilgjengelig"

    shares = amount / price
    portfolio["cash"] = round(cash - amount, 2)
    portfolio.setdefault("positions", {})[ticker] = {
        "shares": shares,
        "avg_price": price,
        "last_price": price,
        "highest_price": price,
        "stop_loss": round(price * (1 - STOP_LOSS_PCT), 4),
        "trailing_stop_pct": TRAILING_STOP_PCT,
        "entry_time": datetime.utcnow().isoformat(),
        "entry_signal": decision,
    }

    portfolio.setdefault("trades", []).append({
        "time": datetime.utcnow().isoformat(),
        "type": "BUY",
        "ticker": ticker,
        "price": round(price, 4),
        "shares": round(shares, 6),
        "amount": round(amount, 2),
        "decision": decision,
    })
    _inc_trade_count(portfolio)
    save_portfolio(portfolio)
    return True, f"Paper BUY {ticker}"


def paper_sell(ticker, price, decision, reason="SELL signal"):
    price = float(price)
    portfolio = load_portfolio()
    positions = portfolio.setdefault("positions", {})

    if ticker not in positions:
        return False, "Ingen posisjon å selge"

    if not can_trade_today(portfolio):
        return False, f"Maks {MAX_TRADES_PER_DAY} trades per dag nådd"

    pos = positions[ticker]
    shares = float(pos.get("shares", 0))
    amount = shares * price
    entry_price = float(pos.get("avg_price", price))
    pnl_pct = ((price - entry_price) / entry_price * 100) if entry_price else 0

    portfolio["cash"] = round(float(portfolio.get("cash", 0)) + amount, 2)

    portfolio.setdefault("trades", []).append({
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

    del positions[ticker]
    _inc_trade_count(portfolio)
    save_portfolio(portfolio)
    return True, f"Paper SELL {ticker}, PnL {pnl_pct:.2f}%"


def apply_risk_exits(ticker, price):
    portfolio = load_portfolio()
    pos = portfolio.get("positions", {}).get(ticker)

    if not pos:
        return False, "Ingen posisjon"

    # Update highest price before checking trailing stop
    pos["last_price"] = float(price)
    pos["highest_price"] = max(float(pos.get("highest_price", price)), float(price))
    save_portfolio(portfolio)

    if should_stop_loss(pos, price):
        return paper_sell(ticker, price, {"decision": "STOP LOSS"}, reason="Stop-loss")

    if should_trailing_stop(pos, price):
        return paper_sell(ticker, price, {"decision": "TRAILING STOP"}, reason="Trailing stop")

    return False, "Ingen risk-exit"


def reset_portfolio():
    portfolio = _empty_portfolio()
    save_portfolio(portfolio)
    return portfolio


def performance_stats(portfolio, latest_prices=None):
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
        "trades_today": trades_today(portfolio),
        "max_trades_per_day": MAX_TRADES_PER_DAY,
    }
