
from datetime import datetime
import pytz

def get_open_markets():
    now = datetime.now(pytz.timezone("Europe/Oslo"))

    if now.weekday() >= 5:
        return []

    hour = now.hour
    minute = now.minute

    open_markets = []

    # USA
    if (hour > 15 or (hour == 15 and minute >= 30)) and hour < 22:
        open_markets.append("USA")

    # Norway
    if hour >= 9 and (hour < 16 or (hour == 16 and minute <= 25)):
        open_markets.append("NORGE")

    # Sweden
    if hour >= 9 and (hour < 17 or (hour == 17 and minute <= 30)):
        open_markets.append("SVERIGE")

    return open_markets


from datetime import datetime
import pytz

def market_is_open():
    now = datetime.now(pytz.timezone("Europe/Oslo"))

    if now.weekday() >= 5:
        return False

    hour = now.hour
    minute = now.minute

    if (hour > 15 or (hour == 15 and minute >= 30)) and hour < 22:
        return True

    if hour >= 9 and hour < 17:
        return True

    return False

if not market_is_open():
    print("⏸ Market closed - skipping run")
    exit()

import os
import time
import pandas as pd

from stocks import get_sp500_tickers, get_norwegian_tickers, get_swedish_tickers, get_all_tickers
from analysis import score_stock
from technical import calculate_rsi, calculate_macd
from patterns import detect_head_shoulders, detect_inverse_head_shoulders, breakout_scanner
from trading_engine import build_trading_decision
from signal_engine import calculate_signal_intelligence
from insider import get_insider_data
from analyst import get_analyst_trend
from earnings import get_earnings
from app import send_pushover_alert
from paper_trading import paper_buy, paper_sell, update_last_price, load_portfolio, portfolio_value, apply_risk_exits, performance_stats

MARKET = os.getenv("SCANNER_MARKET", "ALL").upper()  # USA, NORGE, SVERIGE, ALL
MAX_TICKERS = int(os.getenv("SCANNER_MAX_TICKERS", "30"))
MIN_CONFIDENCE = int(os.getenv("SCANNER_MIN_CONFIDENCE", "70"))
PAPER_TRADING_ENABLED = os.getenv("PAPER_TRADING_ENABLED", "true").lower() == "true"
SCAN_SLEEP_SECONDS = float(os.getenv("SCAN_SLEEP_SECONDS", "0.5"))


def get_watchlist():
    custom = os.getenv("SCANNER_WATCHLIST", "").strip()

    if custom:
        return [x.strip().upper() for x in custom.replace(";", ",").split(",") if x.strip()]

    if MARKET == "USA":
        return get_sp500_tickers(MAX_TICKERS)
    if MARKET == "NORGE":
        return get_norwegian_tickers(MAX_TICKERS)
    if MARKET == "SVERIGE":
        return get_swedish_tickers(MAX_TICKERS)

    return get_all_tickers(limit_per_market=max(5, MAX_TICKERS // 3))[:MAX_TICKERS]


def analyze_ticker(ticker):
    item = score_stock(ticker, use_news=False)
    if not item:
        return None

    df = item["hist"].copy()

    rsi = calculate_rsi(df)
    macd, macd_signal, _ = calculate_macd(df)

    latest_rsi = rsi.dropna().iloc[-1] if not rsi.dropna().empty else 50
    latest_macd = macd.dropna().iloc[-1] if not macd.dropna().empty else 0
    latest_macd_signal = macd_signal.dropna().iloc[-1] if not macd_signal.dropna().empty else 0

    hs = detect_head_shoulders(df)
    inv_hs = detect_inverse_head_shoulders(df)
    breakout = breakout_scanner(df)

    technical_context = {
        "rsi": latest_rsi,
        "macd_bullish": latest_macd > latest_macd_signal,
        "breakout_type": breakout.get("type", "neutral"),
        "head_shoulders_found": hs.get("found", False),
        "inverse_head_shoulders_found": inv_hs.get("found", False),
    }

    decision = build_trading_decision(item, technical_context)

    insider = get_insider_data(ticker)
    analyst = get_analyst_trend(ticker)
    earnings = get_earnings(ticker)

    si = calculate_signal_intelligence(
        item,
        technical_context=technical_context,
        insider=insider,
        analyst=analyst,
        earnings=earnings,
    )

    decision["decision"] = si["decision"]
    decision["emoji"] = si["emoji"]
    decision["confidence"] = si["confidence"]
    decision["decision_score"] = si["final_score"]

    return {
        "ticker": ticker,
        "item": item,
        "price": float(df["Close"].iloc[-1]),
        "decision": decision,
        "signal_intelligence": si,
        "rsi": float(latest_rsi),
    }


def run_once():
    
markets = get_open_markets()

if not markets:
    print("⏸ Alle markeder stengt")
    exit()

print(f"Åpne markeder: {markets}")

tickers = []

if "USA" in markets:
    tickers += get_sp500_tickers(20)

if "NORGE" in markets:
    tickers += get_norwegian_tickers(5)

if "SVERIGE" in markets:
    tickers += get_swedish_tickers(5)

    print(f"Scanner {len(tickers)} tickers: {tickers}")

    latest_prices = {}

    for ticker in tickers:
        try:
            result = analyze_ticker(ticker)
            if not result:
                continue

            ticker = result["ticker"]
            price = result["price"]
            decision = result["decision"]
            signal = decision.get("decision")
            confidence = int(decision.get("confidence", 0))
            latest_prices[ticker] = price
            update_last_price(ticker, price)

            print(f"{ticker}: {signal} conf={confidence} price={price}")

            if confidence < MIN_CONFIDENCE:
                continue

            if PAPER_TRADING_ENABLED:
                if signal == "BUY":
                    ok, msg = paper_buy(ticker, price, decision)
                    if ok:
                        send_pushover_alert(f"🧪 {msg}\\nPris: {price}\\nConfidence: {confidence}%", title="Paper Trading")
                elif signal == "SELL / AVOID":
                    ok, msg = paper_sell(ticker, price, decision)
                    if ok:
                        send_pushover_alert(f"🧪 {msg}\\nPris: {price}\\nConfidence: {confidence}%", title="Paper Trading")

            time.sleep(SCAN_SLEEP_SECONDS)

        except Exception as e:
            print(f"Feil på {ticker}: {e}")

    portfolio = load_portfolio()
    value = portfolio_value(portfolio, latest_prices)
    print(f"Portfolio value: {value}")
    return value


if __name__ == "__main__":
    run_once()
