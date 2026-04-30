
from paper_store import load_portfolio, save_portfolio, add_trade

POSITION_SIZE_PCT = 10.0
MAX_OPEN_POSITIONS = 5

STOP_LOSS_PCT = 7.0
TAKE_PROFIT_PCT = 12.0
TRAILING_STOP_PCT = 8.0
MIN_BUY_CONFIDENCE = 60

RSI_SELL_LEVEL = 75.0


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


def normalize_signal(signal):
    s = str(signal or "").upper().strip()
    if "BUY" in s:
        return "BUY"
    if "SELL" in s or "AVOID" in s:
        return "SELL"
    if "HOLD" in s or "WAIT" in s:
        return "HOLD"
    return s or "HOLD"


def update_position_levels(position, current_price):
    entry = float(position.get("entry_price", current_price))
    current_price = float(current_price)
    old_high = float(position.get("highest_price", entry) or entry)
    new_high = max(old_high, current_price)

    stop_loss, take_profit, trailing_stop = calc_levels(entry, new_high)

    position["last_price"] = current_price
    position["highest_price"] = new_high
    position["stop_loss"] = stop_loss
    position["take_profit"] = take_profit
    position["trailing_stop"] = trailing_stop

    return position


def should_sell(position, current_price, signal, rsi=None, prev_rsi=None):
    """
    Returnerer (True, reason) hvis posisjon skal selges.
    Regler:
    1. SELL/AVOID signal
    2. Stop-loss
    3. Take-profit
    4. Trailing stop
    5. RSI > 75 og faller
    """
    signal = normalize_signal(signal)
    current_price = float(current_price)

    entry = float(position.get("entry_price", current_price))
    stop_loss = float(position.get("stop_loss", 0) or 0)
    take_profit = float(position.get("take_profit", 0) or 0)
    trailing_stop = float(position.get("trailing_stop", 0) or 0)
    highest_price = float(position.get("highest_price", entry) or entry)

    pnl_pct = ((current_price - entry) / entry * 100) if entry else 0

    if signal == "SELL":
        return True, "SELL signal"

    if stop_loss and current_price <= stop_loss:
        return True, f"Stop loss {pnl_pct:.2f}%"

    if take_profit and current_price >= take_profit:
        return True, f"Take profit {pnl_pct:.2f}%"

    # Trailing stop skal først være relevant hvis aksjen faktisk har beveget seg opp fra entry.
    if trailing_stop and highest_price > entry and current_price <= trailing_stop:
        return True, f"Trailing stop {pnl_pct:.2f}%"

    if rsi is not None:
        try:
            rsi_now = float(rsi)
            rsi_prev = float(prev_rsi) if prev_rsi is not None else None
            if rsi_now > RSI_SELL_LEVEL and (rsi_prev is None or rsi_now < rsi_prev):
                return True, f"RSI sell {rsi_now:.1f}"
        except Exception:
            pass

    return False, "Hold"


def paper_buy(ticker, price, confidence=0, reason="BUY signal"):
    portfolio = load_portfolio()
    ticker = str(ticker).upper()
    price = float(price)
    confidence = int(confidence or 0)

    if price <= 0:
        return False, "Ugyldig pris"

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
        "ticker": ticker,
        "shares": shares,
        "entry_price": price,
        "last_price": price,
        "highest_price": price,
        "stop_loss": stop_loss,
        "take_profit": take_profit,
        "trailing_stop": trailing_stop,
        "confidence": confidence,
        "reason": reason,
        "opened_at": "",
    }

    add_trade(portfolio, {
        "type": "BUY",
        "ticker": ticker,
        "price": round(price, 2),
        "shares": round(shares, 6),
        "amount": round(amount, 2),
        "confidence": confidence,
        "reason": reason,
    })

    return True, f"BUY {ticker} @ {price:.2f}"


def paper_sell(ticker, price, reason="SELL signal"):
    portfolio = load_portfolio()
    ticker = str(ticker).upper()
    price = float(price)

    pos = portfolio["positions"].get(ticker)
    if not pos:
        return False, f"Ingen posisjon i {ticker}"

    shares = float(pos.get("shares", 0))
    amount = shares * price
    entry = float(pos.get("entry_price", price))
    pnl_pct = ((price - entry) / entry * 100) if entry else 0

    portfolio["cash"] = round(float(portfolio["cash"]) + amount, 2)
    del portfolio["positions"][ticker]

    add_trade(portfolio, {
        "type": "SELL",
        "ticker": ticker,
        "price": round(price, 2),
        "shares": round(shares, 6),
        "amount": round(amount, 2),
        "confidence": int(pos.get("confidence", 0) or 0),
        "pnl_pct": round(pnl_pct, 2),
        "reason": reason,
    })

    return True, f"SELL {ticker} @ {price:.2f} ({pnl_pct:.2f}%)"


def auto_trade(ticker, price, signal, confidence=0, rsi=None, prev_rsi=None):
    """
    Hovedmotor:
    - Hvis posisjon finnes: oppdater nivåer og vurder SELL først.
    - Hvis ingen posisjon finnes: vurder BUY.
    """
    portfolio = load_portfolio()
    ticker = str(ticker).upper()
    price = float(price)
    signal = normalize_signal(signal)

    pos = portfolio["positions"].get(ticker)

    if pos:
        pos = update_position_levels(pos, price)
        portfolio["positions"][ticker] = pos
        save_portfolio(portfolio)

        sell_ok, sell_reason = should_sell(pos, price, signal, rsi=rsi, prev_rsi=prev_rsi)
        if sell_ok:
            return paper_sell(ticker, price, sell_reason)

        return False, f"HOLD {ticker}"

    if signal == "BUY":
        return paper_buy(ticker, price, confidence, "BUY signal")

    return False, "Ingen trade"
