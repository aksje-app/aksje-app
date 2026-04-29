import json
import os
from datetime import datetime
from pathlib import Path

PORTFOLIO_FILE = Path(os.getenv("PAPER_PORTFOLIO_FILE", "paper_portfolio.json"))

DEFAULT_START_CASH = float(os.getenv("PAPER_START_CASH", "100000"))
DEFAULT_POSITION_SIZE = float(os.getenv("PAPER_POSITION_SIZE", "10000"))


def _empty_portfolio():
    return {
        "cash": DEFAULT_START_CASH,
        "positions": {},
        "trades": [],
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
            return json.load(f)
    except Exception:
        portfolio = _empty_portfolio()
        save_portfolio(portfolio)
        return portfolio


def save_portfolio(portfolio):
    portfolio["updated_at"] = datetime.utcnow().isoformat()
    with open(PORTFOLIO_FILE, "w", encoding="utf-8") as f:
        json.dump(portfolio, f, indent=2, ensure_ascii=False)


def portfolio_value(portfolio, latest_prices=None):
    latest_prices = latest_prices or {}
    value = float(portfolio.get("cash", 0))

    for ticker, pos in portfolio.get("positions", {}).items():
        shares = float(pos.get("shares", 0))
        price = latest_prices.get(ticker, pos.get("last_price", pos.get("avg_price", 0)))
        value += shares * float(price or 0)

    return round(value, 2)


def paper_buy(ticker, price, decision, amount=None):
    amount = float(amount or DEFAULT_POSITION_SIZE)
    price = float(price)

    if price <= 0:
        return False, "Ugyldig pris"

    portfolio = load_portfolio()
    cash = float(portfolio.get("cash", 0))

    if cash < amount:
        amount = cash

    if amount <= 0:
        return False, "Ingen cash tilgjengelig"

    # Ikke kjøp mer hvis vi allerede har posisjon.
    if ticker in portfolio.get("positions", {}):
        return False, "Har allerede posisjon"

    shares = amount / price
    portfolio["cash"] = round(cash - amount, 2)
    portfolio.setdefault("positions", {})[ticker] = {
        "shares": shares,
        "avg_price": price,
        "last_price": price,
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

    save_portfolio(portfolio)
    return True, f"Paper BUY {ticker}"


def paper_sell(ticker, price, decision):
    price = float(price)

    portfolio = load_portfolio()
    positions = portfolio.setdefault("positions", {})

    if ticker not in positions:
        return False, "Ingen posisjon å selge"

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
        "decision": decision,
    })

    del positions[ticker]
    save_portfolio(portfolio)
    return True, f"Paper SELL {ticker}, PnL {pnl_pct:.2f}%"


def update_last_price(ticker, price):
    portfolio = load_portfolio()
    if ticker in portfolio.get("positions", {}):
        portfolio["positions"][ticker]["last_price"] = float(price)
        save_portfolio(portfolio)


def reset_portfolio():
    portfolio = _empty_portfolio()
    save_portfolio(portfolio)
    return portfolio
