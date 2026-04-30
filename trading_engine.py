
from paper_store import load_portfolio, save_portfolio, add_trade

POSITION_SIZE_PCT = 10.0
MAX_OPEN_POSITIONS = 5
STOP_LOSS_PCT = 7.0
TAKE_PROFIT_PCT = 12.0
TRAILING_STOP_PCT = 8.0
MIN_BUY_CONFIDENCE = 60

def portfolio_value(portfolio=None, latest_prices=None):
    portfolio = portfolio or load_portfolio()
    latest_prices = latest_prices or {}
    total = float(portfolio.get("cash", 0))
    for ticker, pos in portfolio.get("positions", {}).items():
        price = latest_prices.get(ticker, pos.get("last_price", pos.get("entry_price", 0)))
        total += float(pos.get("shares", 0)) * float(price or 0)
    return round(total, 2)

def calc_levels(entry_price, highest_price=None):
    entry_price = float(entry_price)
    highest_price = float(highest_price or entry_price)
    stop_loss = entry_price * (1 - STOP_LOSS_PCT / 100)
    take_profit = entry_price * (1 + TAKE_PROFIT_PCT / 100)
    trailing_stop = highest_price * (1 - TRAILING_STOP_PCT / 100)
    return round(stop_loss, 2), round(take_profit, 2), round(trailing_stop, 2)

def paper_buy(ticker, price, confidence=0, reason="BUY signal"):
    portfolio = load_portfolio()
    ticker = ticker.upper()
    price = float(price)
    if ticker in portfolio["positions"]:
        return False, f"{ticker} eies allerede"
    if len(portfolio["positions"]) >= MAX_OPEN_POSITIONS:
        return False, "Maks åpne posisjoner nådd"
    if confidence < MIN_BUY_CONFIDENCE:
        return False, "Confidence for lav"
    total_value = portfolio_value(portfolio)
    amount = min(float(portfolio["cash"]), total_value * POSITION_SIZE_PCT / 100)
    if amount <= 0:
        return False, "Ikke nok cash"
    shares = amount / price
    stop_loss, take_profit, trailing_stop = calc_levels(price, price)
    portfolio["cash"] = round(float(portfolio["cash"]) - amount, 2)
    portfolio["positions"][ticker] = {
        "ticker": ticker, "shares": shares, "entry_price": price, "last_price": price,
        "highest_price": price, "stop_loss": stop_loss, "take_profit": take_profit,
        "trailing_stop": trailing_stop, "confidence": confidence, "reason": reason, "opened_at": "",
    }
    add_trade(portfolio, {"type": "BUY", "ticker": ticker, "price": round(price, 2),
                          "shares": round(shares, 6), "amount": round(amount, 2),
                          "confidence": confidence, "reason": reason})
    return True, f"BUY {ticker} @ {price:.2f}"

def paper_sell(ticker, price, reason="SELL signal"):
    portfolio = load_portfolio()
    ticker = ticker.upper()
    price = float(price)
    pos = portfolio["positions"].get(ticker)
    if not pos:
        return False, f"Ingen posisjon i {ticker}"
    shares = float(pos["shares"])
    amount = shares * price
    entry = float(pos["entry_price"])
    pnl_pct = ((price - entry) / entry * 100) if entry else 0
    portfolio["cash"] = round(float(portfolio["cash"]) + amount, 2)
    del portfolio["positions"][ticker]
    add_trade(portfolio, {"type": "SELL", "ticker": ticker, "price": round(price, 2),
                          "shares": round(shares, 6), "amount": round(amount, 2),
                          "confidence": int(pos.get("confidence", 0)), "pnl_pct": round(pnl_pct, 2),
                          "reason": reason})
    return True, f"SELL {ticker} @ {price:.2f} ({pnl_pct:.2f}%)"

def auto_trade(ticker, price, signal, confidence=0):
    portfolio = load_portfolio()
    ticker = ticker.upper()
    price = float(price)
    signal = str(signal).upper()
    pos = portfolio["positions"].get(ticker)
    if pos:
        entry = float(pos["entry_price"])
        old_high = float(pos.get("highest_price", entry))
        new_high = max(old_high, price)
        stop_loss, take_profit, trailing_stop = calc_levels(entry, new_high)
        pos["last_price"] = price
        pos["highest_price"] = new_high
        pos["stop_loss"] = stop_loss
        pos["take_profit"] = take_profit
        pos["trailing_stop"] = trailing_stop
        portfolio["positions"][ticker] = pos
        save_portfolio(portfolio)
        pnl_pct = ((price - entry) / entry * 100) if entry else 0
        if signal in ["SELL", "SELL / AVOID", "AVOID"]:
            return paper_sell(ticker, price, "SELL signal")
        if price <= stop_loss:
            return paper_sell(ticker, price, f"Stop loss {pnl_pct:.2f}%")
        if price >= take_profit:
            return paper_sell(ticker, price, f"Take profit {pnl_pct:.2f}%")
        if price <= trailing_stop and new_high > entry:
            return paper_sell(ticker, price, f"Trailing stop {pnl_pct:.2f}%")
        return False, f"HOLD {ticker}"
    if signal == "BUY":
        return paper_buy(ticker, price, confidence, "BUY signal")
    return False, "Ingen trade"
