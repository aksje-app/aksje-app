
from paper_store import load_portfolio, save_portfolio, add_trade

POSITION_SIZE_PCT = 10.0
MAX_OPEN_POSITIONS = 5
STOP_LOSS_PCT = 7.0
TAKE_PROFIT_PCT = 12.0
TRAILING_STOP_PCT = 8.0
MIN_BUY_CONFIDENCE = 60


def build_trading_decision(item, technical_context=None):
    technical_context = technical_context or {}
    score = float(item.get("score", 0) or 0)
    rsi = float(technical_context.get("rsi", 50) or 50)
    macd_bullish = bool(technical_context.get("macd_bullish", False))
    breakout_type = technical_context.get("breakout_type", "neutral")

    buy_points = 0
    sell_points = 0
    reasons = []

    if score >= 7:
        buy_points += 3; reasons.append("Sterk totalscore")
    elif score >= 6:
        buy_points += 2; reasons.append("God totalscore")
    elif score < 4:
        sell_points += 2; reasons.append("Svak totalscore")

    if rsi < 30:
        buy_points += 2; reasons.append("RSI oversolgt")
    elif rsi > 75:
        sell_points += 2; reasons.append("RSI høyt/overkjøpt")
    elif 40 <= rsi <= 65:
        buy_points += 1; reasons.append("RSI i sunn sone")

    if macd_bullish:
        buy_points += 1; reasons.append("MACD bullish")
    else:
        sell_points += 1; reasons.append("MACD bearish")

    if breakout_type == "bullish":
        buy_points += 2; reasons.append("Bullish breakout")
    elif breakout_type == "bearish":
        sell_points += 2; reasons.append("Bearish breakdown")

    decision_score = max(0, min(10, round(score + (buy_points - sell_points) * 0.35, 2)))
    confidence = int(max(35, min(95, 45 + decision_score * 5 + (buy_points - sell_points) * 3)))

    if buy_points >= sell_points + 2 and decision_score >= 6.0:
        decision, emoji = "BUY", "🟢"
    elif sell_points >= buy_points + 2:
        decision, emoji = "SELL / AVOID", "🔴"
    else:
        decision, emoji = "HOLD / WAIT", "🟡"

    return {
        "decision": decision,
        "emoji": emoji,
        "confidence": confidence,
        "decision_score": decision_score,
        "buy_points": buy_points,
        "sell_points": sell_points,
        "reasons": reasons,
    }


def adjusted_score(item, decision):
    base = float(item.get("score", 0) or 0)
    if decision.get("decision") == "BUY":
        return round(min(10, base + 0.5), 2)
    if "SELL" in decision.get("decision", ""):
        return round(max(0, base - 0.8), 2)
    return round(base, 2)


def portfolio_value(portfolio=None, latest_prices=None):
    portfolio = portfolio or load_portfolio()
    latest_prices = latest_prices or {}
    total = float(portfolio.get("cash", 0))
    for ticker, pos in portfolio.get("positions", {}).items():
        entry = pos.get("entry_price", pos.get("avg_price", 0))
        price = latest_prices.get(ticker, pos.get("last_price", entry))
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
    ticker = str(ticker).upper()
    price = float(price)
    if ticker in portfolio.get("positions", {}):
        return False, f"{ticker} eies allerede"
    if len(portfolio.get("positions", {})) >= MAX_OPEN_POSITIONS:
        return False, "Maks åpne posisjoner nådd"
    if int(confidence or 0) < MIN_BUY_CONFIDENCE:
        return False, "Confidence for lav"
    total_value = portfolio_value(portfolio)
    amount = min(float(portfolio.get("cash", 0)), total_value * POSITION_SIZE_PCT / 100)
    if amount <= 0:
        return False, "Ikke nok cash"
    shares = amount / price
    sl, tp, tr = calc_levels(price, price)
    portfolio["cash"] = round(float(portfolio.get("cash", 0)) - amount, 2)
    portfolio.setdefault("positions", {})[ticker] = {
        "ticker": ticker, "shares": shares, "entry_price": price, "avg_price": price,
        "last_price": price, "highest_price": price, "stop_loss": sl,
        "take_profit": tp, "trailing_stop": tr, "confidence": int(confidence or 0), "reason": reason,
    }
    add_trade(portfolio, {"type":"BUY", "ticker":ticker, "price":round(price,2), "shares":round(shares,6), "amount":round(amount,2), "confidence":int(confidence or 0), "reason":reason})
    return True, f"BUY {ticker} @ {price:.2f}"


def paper_sell(ticker, price, reason="SELL signal"):
    portfolio = load_portfolio()
    ticker = str(ticker).upper()
    price = float(price)
    pos = portfolio.get("positions", {}).get(ticker)
    if not pos:
        return False, f"Ingen posisjon i {ticker}"
    shares = float(pos.get("shares", 0))
    entry = float(pos.get("entry_price", pos.get("avg_price", price)))
    amount = shares * price
    pnl_pct = ((price-entry)/entry*100) if entry else 0
    portfolio["cash"] = round(float(portfolio.get("cash", 0)) + amount, 2)
    del portfolio["positions"][ticker]
    add_trade(portfolio, {"type":"SELL", "ticker":ticker, "price":round(price,2), "shares":round(shares,6), "amount":round(amount,2), "confidence":int(pos.get("confidence",0) or 0), "pnl_pct":round(pnl_pct,2), "reason":reason})
    return True, f"SELL {ticker} @ {price:.2f} ({pnl_pct:.2f}%)"


def auto_trade(ticker, price, signal, confidence=0, rsi=None, prev_rsi=None):
    portfolio = load_portfolio()
    ticker = str(ticker).upper()
    price = float(price)
    sig = str(signal or "").upper()
    pos = portfolio.get("positions", {}).get(ticker)
    if pos:
        entry = float(pos.get("entry_price", pos.get("avg_price", price)))
        high = max(float(pos.get("highest_price", entry) or entry), price)
        sl, tp, tr = calc_levels(entry, high)
        pos.update({"last_price":price, "highest_price":high, "stop_loss":sl, "take_profit":tp, "trailing_stop":tr})
        portfolio["positions"][ticker] = pos
        save_portfolio(portfolio)
        pnl_pct = ((price-entry)/entry*100) if entry else 0
        if "SELL" in sig or "AVOID" in sig:
            return paper_sell(ticker, price, "SELL signal")
        if price <= sl:
            return paper_sell(ticker, price, f"Stop loss {pnl_pct:.2f}%")
        if price >= tp:
            return paper_sell(ticker, price, f"Take profit {pnl_pct:.2f}%")
        if high > entry and price <= tr:
            return paper_sell(ticker, price, f"Trailing stop {pnl_pct:.2f}%")
        try:
            if rsi is not None and float(rsi) > 75 and (prev_rsi is None or float(rsi) < float(prev_rsi)):
                return paper_sell(ticker, price, f"RSI sell {float(rsi):.1f}")
        except Exception:
            pass
        return False, f"HOLD {ticker}"
    if "BUY" in sig:
        return paper_buy(ticker, price, confidence, "BUY signal")
    return False, "Ingen trade"
