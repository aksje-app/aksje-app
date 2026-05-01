from signal_engine import score_signal
from notifier import notify_trade
from trading_settings import load_rules

from paper_store import load_portfolio, save_portfolio, add_trade

POSITION_SIZE_PCT = 10.0
MAX_OPEN_POSITIONS = 5
STOP_LOSS_PCT = 7.0
TAKE_PROFIT_PCT = 12.0
TRAILING_STOP_PCT = 8.0
MIN_BUY_CONFIDENCE = 60


def build_trading_decision(item, technical_context=None):
    """
    Smart Core v2 wrapper.
    Beholder app13-kompatibelt output.
    """
    return score_signal(item, technical_context or {})




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
    """
    Bruker lagrede trading-regler, slik at stop-loss/take-profit/trailing
    er likt i sidebar, paper trading og auto trading.
    """
    rules = load_rules()
    entry_price = float(entry_price)
    highest_price = float(highest_price or entry_price)

    stop_loss_pct = float(rules.get("stop_loss_pct", STOP_LOSS_PCT))
    take_profit_pct = float(rules.get("take_profit_pct", TAKE_PROFIT_PCT))
    trailing_stop_pct = float(rules.get("trailing_stop_pct", TRAILING_STOP_PCT))

    stop_loss = entry_price * (1 - stop_loss_pct / 100)
    take_profit = entry_price * (1 + take_profit_pct / 100)
    trailing_stop = highest_price * (1 - trailing_stop_pct / 100)

    return round(stop_loss, 2), round(take_profit, 2), round(trailing_stop, 2)






def notify_executed_trade(trade_type, ticker, price, shares=None, amount=None, confidence=None, reason=""):
    """
    Sentral varsling for ALLE faktiske paper trades:
    - Cron BUY/SELL
    - UI paper-kjøp/paper-selg
    - Stop-loss
    - Take-profit
    - Trailing stop

    Feil i Pushover skal aldri stoppe selve handelen.
    """
    try:
        parts = [
            f"{trade_type.upper()}: {ticker}",
            f"Pris: {float(price):.2f}",
        ]

        if shares is not None:
            parts.append(f"Antall: {float(shares):.4f}")
        if amount is not None:
            parts.append(f"Beløp: {float(amount):.2f}")
        if confidence is not None:
            parts.append(f"Confidence: {int(confidence)}%")
        if reason:
            parts.append(f"Årsak: {reason}")

        return notify_trade(
            trade_type,
            ticker,
            price,
            amount=amount,
            shares=shares,
            confidence=confidence,
            reason=reason,
        )
    except Exception as e:
        print(f"notify_executed_trade failed: {e}")
        return False


def paper_buy(ticker, price, confidence=0, reason="BUY signal"):
    rules = load_rules()
    max_open_positions = int(rules.get("max_open_positions", MAX_OPEN_POSITIONS))
    min_buy_confidence = int(rules.get("min_buy_confidence", MIN_BUY_CONFIDENCE))
    position_size_pct = float(rules.get("position_size_pct", POSITION_SIZE_PCT))
    portfolio = load_portfolio()
    ticker = str(ticker).upper()
    price = float(price)
    if ticker in portfolio.get("positions", {}):
        return False, f"{ticker} eies allerede"
    if len(portfolio.get("positions", {})) >= max_open_positions:
        return False, "Maks åpne posisjoner nådd"
    if int(confidence or 0) < min_buy_confidence:
        return False, "Confidence for lav"
    total_value = portfolio_value(portfolio)
    amount = min(float(portfolio.get("cash", 0)), total_value * position_size_pct / 100)
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
    notify_executed_trade("BUY", ticker, price, shares=shares, amount=amount, confidence=confidence, reason=reason)
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
    notify_executed_trade("SELL", ticker, price, shares=shares, amount=amount, confidence=pos.get("confidence"), reason=reason)
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


# -------------------------------------------------------------------
# Pro signal tuning v1
# Conservative rules to reduce bad BUYs:
# - no BUY when RSI is high/overbought
# - prefer BUY only with good score + MACD/breakout support
# -------------------------------------------------------------------
def pro_signal_from_context(base_score, technical_context=None):
    technical_context = technical_context or {}
    try:
        score = float(base_score or 0)
    except Exception:
        score = 0.0

    try:
        rsi = float(technical_context.get("rsi", 50))
    except Exception:
        rsi = 50.0

    macd_bullish = bool(technical_context.get("macd_bullish", False))
    breakout_type = str(technical_context.get("breakout_type", "neutral")).lower()

    buy_ok = (
        score >= 7.0
        and rsi < 70
        and (macd_bullish or breakout_type in ["bullish", "breakout", "up"])
    )

    sell_avoid = (
        score <= 4.0
        or rsi >= 78
        or breakout_type in ["bearish", "breakdown", "down"]
    )

    return buy_ok, sell_avoid, rsi, macd_bullish, breakout_type
