
import json
import os
from pathlib import Path
from datetime import datetime

STORE_FILE = Path("paper_portfolio.json")

DEFAULT_PORTFOLIO = {
    "cash": 100000.0,
    "positions": {},
    "trades": []
}


def load_portfolio():
    if not STORE_FILE.exists():
        save_portfolio(DEFAULT_PORTFOLIO.copy())
        return DEFAULT_PORTFOLIO.copy()

    try:
        with open(STORE_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception:
        data = DEFAULT_PORTFOLIO.copy()

    data.setdefault("cash", 100000.0)
    data.setdefault("positions", {})
    data.setdefault("trades", [])
    return data


def save_portfolio(portfolio):
    with open(STORE_FILE, "w", encoding="utf-8") as f:
        json.dump(portfolio, f, indent=2, ensure_ascii=False)


def reset_portfolio(start_cash=100000.0):
    p = {
        "cash": float(start_cash),
        "positions": {},
        "trades": []
    }
    save_portfolio(p)
    return p


def add_trade(portfolio, trade):
    trade["time"] = datetime.now().isoformat(timespec="seconds")
    portfolio["trades"].insert(0, trade)
    save_portfolio(portfolio)
