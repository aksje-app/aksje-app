from datetime import datetime
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







def trades_today_count(portfolio=None, trade_type=None):
    """
    Teller handler i dag basert på paper portfolio trade-logg.
    Brukes for å hindre at auto-kjøp spammer posisjoner.
    """
    portfolio = portfolio or load_portfolio()
    today = datetime.now().date().isoformat()
    count = 0

    for trade in portfolio.get("trades", []):
        t = str(trade.get("time", ""))
        if not t.startswith(today):
            continue
        if trade_type and str(trade.get("type", "")).upper() != str(trade_type).upper():
            continue
        count += 1

    return count


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
    max_trades_per_day = int(rules.get("max_trades_per_day", 3))
    min_buy_confidence = int(rules.get("min_buy_confidence", MIN_BUY_CONFIDENCE))
    position_size_pct = float(rules.get("position_size_pct", POSITION_SIZE_PCT))
    portfolio = load_portfolio()
    ticker = str(ticker).upper()
    price = float(price)
    if price <= 0:
        return False, "Ugyldig prisdata - kjøp stoppet"
    if ticker in portfolio.get("positions", {}):
        return False, f"{ticker} eies allerede"
    if len(portfolio.get("positions", {})) >= max_open_positions:
        return False, "Maks åpne posisjoner nådd"
    if int(confidence or 0) < min_buy_confidence:
        return False, f"Confidence for lav ({int(confidence or 0)} < {min_buy_confidence})"
    # V12: dagsgrensen gjelder kun nye kjøp, ikke salg/exit.
    if trades_today_count(portfolio, trade_type="BUY") >= max_trades_per_day:
        return False, f"Maks kjøp per dag nådd ({max_trades_per_day})"
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
# v18.5.45: Paper trading support for funds and ETFs
# -------------------------------------------------------------------
FUND_ASSET_TYPES = {"ETF", "Fond", "Indeksfond", "Aktivt fond"}


def _normalize_paper_symbol(symbol):
    return str(symbol or "").strip().upper()


def _normalize_asset_type(asset_type):
    text = str(asset_type or "").strip()
    if text.lower() in {"etf", "exchange traded fund"}:
        return "ETF"
    if text.lower() in {"indeks", "indeksfond", "index fund"}:
        return "Indeksfond"
    if text.lower() in {"aktivt", "aktivt fond", "active fund"}:
        return "Aktivt fond"
    if text.lower() in {"fond", "fund"}:
        return "Fond"
    return text or "Aksje"


def _units_label_for_asset(asset_type):
    asset_type = _normalize_asset_type(asset_type)
    if asset_type in FUND_ASSET_TYPES:
        return "andeler" if asset_type != "ETF" else "units"
    return "shares"


def paper_buy_instrument(
    symbol,
    price,
    amount,
    asset_type="ETF",
    confidence=0,
    reason="Manuelt paper-kjøp",
    currency="NOK",
    nav_date="",
    purchase_mode="Engangskjøp",
):
    """Buy a paper-trading instrument by amount.

    v18.5.45: Supports ETF/fund accumulation. Unlike the legacy stock
    paper_buy(), this function can add to an existing fund/ETF position and uses
    a user-selected amount instead of position-size rules.
    """
    symbol = _normalize_paper_symbol(symbol)
    asset_type = _normalize_asset_type(asset_type)
    currency = str(currency or "NOK").upper()
    try:
        price = float(price)
        amount = float(amount)
    except Exception:
        return False, "Ugyldig pris eller beløp"
    if not symbol:
        return False, "Mangler symbol"
    if price <= 0:
        return False, "Ugyldig pris/NAV"
    if amount <= 0:
        return False, "Beløp må være større enn 0"

    portfolio = load_portfolio()
    cash = float(portfolio.get("cash", 0) or 0)
    if cash < amount:
        return False, f"Ikke nok cash ({cash:.2f} tilgjengelig)"

    units = amount / price
    positions = portfolio.setdefault("positions", {})
    existing = positions.get(symbol)
    units_label = _units_label_for_asset(asset_type)
    if existing:
        old_units = float(existing.get("shares", 0) or 0)
        old_avg = float(existing.get("entry_price", existing.get("avg_price", price)) or price)
        new_units = old_units + units
        new_avg = ((old_units * old_avg) + amount) / new_units if new_units else price
        existing.update({
            "ticker": symbol,
            "shares": new_units,
            "entry_price": round(new_avg, 6),
            "avg_price": round(new_avg, 6),
            "last_price": price,
            "highest_price": max(float(existing.get("highest_price", price) or price), price),
            "asset_type": asset_type,
            "units_label": units_label,
            "currency": currency,
            "nav_date": nav_date or existing.get("nav_date", ""),
            "purchase_mode": purchase_mode,
            "confidence": int(confidence or existing.get("confidence", 0) or 0),
            "reason": reason,
        })
    else:
        sl, tp, tr = calc_levels(price, price)
        positions[symbol] = {
            "ticker": symbol,
            "shares": units,
            "entry_price": price,
            "avg_price": price,
            "last_price": price,
            "highest_price": price,
            "stop_loss": 0 if asset_type in FUND_ASSET_TYPES else sl,
            "take_profit": 0 if asset_type in FUND_ASSET_TYPES else tp,
            "trailing_stop": 0 if asset_type in FUND_ASSET_TYPES else tr,
            "confidence": int(confidence or 0),
            "reason": reason,
            "opened_at": datetime.now().isoformat(timespec="seconds"),
            "asset_type": asset_type,
            "units_label": units_label,
            "currency": currency,
            "nav_date": nav_date,
            "purchase_mode": purchase_mode,
        }

    portfolio["cash"] = round(cash - amount, 2)
    add_trade(portfolio, {
        "type": "BUY",
        "ticker": symbol,
        "price": round(price, 6),
        "shares": round(units, 8),
        "amount": round(amount, 2),
        "confidence": int(confidence or 0),
        "reason": reason,
        "asset_type": asset_type,
        "currency": currency,
        "nav_date": nav_date,
        "order_kind": "amount_buy",
    })
    notify_executed_trade("BUY", symbol, price, shares=units, amount=amount, confidence=confidence, reason=reason)
    return True, f"KJØP {asset_type} {symbol}: {amount:.2f} {currency} @ {price:.4f}"


def paper_sell_instrument(symbol, price, sell_amount=None, reason="Manuelt paper-salg", currency="NOK", nav_date=""):
    """Sell all or part of a paper-trading instrument by amount.

    If sell_amount is None, the whole position is sold. If sell_amount is lower
    than current value, only a proportional number of units is sold.
    """
    symbol = _normalize_paper_symbol(symbol)
    try:
        price = float(price)
    except Exception:
        return False, "Ugyldig pris/NAV"
    if not symbol:
        return False, "Mangler symbol"
    if price <= 0:
        return False, "Ugyldig pris/NAV"

    portfolio = load_portfolio()
    pos = portfolio.get("positions", {}).get(symbol)
    if not pos:
        return False, f"Ingen posisjon i {symbol}"

    units = float(pos.get("shares", 0) or 0)
    entry = float(pos.get("entry_price", pos.get("avg_price", price)) or price)
    current_value = units * price
    if current_value <= 0:
        return False, "Posisjonen har ingen verdi"
    if sell_amount is None or float(sell_amount or 0) <= 0 or float(sell_amount or 0) >= current_value:
        units_to_sell = units
        amount = current_value
        close_all = True
    else:
        amount = float(sell_amount)
        units_to_sell = amount / price
        close_all = False

    pnl_pct = ((price - entry) / entry * 100) if entry else 0
    portfolio["cash"] = round(float(portfolio.get("cash", 0) or 0) + amount, 2)
    if close_all:
        del portfolio["positions"][symbol]
    else:
        pos["shares"] = max(0.0, units - units_to_sell)
        pos["last_price"] = price
        pos["nav_date"] = nav_date or pos.get("nav_date", "")
        portfolio["positions"][symbol] = pos

    add_trade(portfolio, {
        "type": "SELL",
        "ticker": symbol,
        "price": round(price, 6),
        "shares": round(units_to_sell, 8),
        "amount": round(amount, 2),
        "confidence": int(pos.get("confidence", 0) or 0),
        "pnl_pct": round(pnl_pct, 2),
        "reason": reason,
        "asset_type": pos.get("asset_type", "Aksje"),
        "currency": currency or pos.get("currency", ""),
        "nav_date": nav_date or pos.get("nav_date", ""),
        "order_kind": "amount_sell" if not close_all else "sell_all",
    })
    notify_executed_trade("SELL", symbol, price, shares=units_to_sell, amount=amount, confidence=pos.get("confidence"), reason=reason)
    suffix = "alt" if close_all else f"{amount:.2f} {currency}"
    return True, f"SALG {symbol}: {suffix} @ {price:.4f} ({pnl_pct:.2f}%)"


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
