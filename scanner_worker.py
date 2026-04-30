
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
from rsi_macd_engine import combo_signal
from alert_state import should_send_alert, record_alert
from market_hours import open_markets, should_process_ticker
from trading_settings import load_rules, should_buy, should_sell
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
from paper_trading import auto_trade, paper_buy, paper_sell, update_last_price, load_portfolio, portfolio_value, apply_risk_exits, performance_stats

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
    decision["rsi_macd_combo"] = combo_signal(rsi, macd, macd_signal)

    return {
        "ticker": ticker,
        "item": item,
        "price": float(df["Close"].iloc[-1]),
        "decision": decision,
        "signal_intelligence": si,
        "rsi": float(latest_rsi),
    }


def run_once():
    rules = load_rules()
    markets = get_open_markets()

    if not markets:
        print("⏸ Alle markeder stengt")
        return 0

    print(f"Åpne markeder: {markets}")

    tickers = []

    custom = os.getenv("SCANNER_WATCHLIST", "").strip()
    if custom:
        tickers = [x.strip().upper() for x in custom.replace(";", ",").split(",") if x.strip()]
    else:
        if "USA" in markets:
            tickers += get_sp500_tickers(20)

        if "NORGE" in markets:
            tickers += get_norwegian_tickers(5)

        if "SVERIGE" in markets:
            tickers += get_swedish_tickers(5)

    tickers = tickers[:MAX_TICKERS]

    if not tickers:
        print("Ingen tickere å scanne.")
        return 0

    print(f"Scanner {len(tickers)} tickers: {tickers}")

    latest_prices = {}
    candidates = []

    for ticker in tickers:
        try:
            if not should_process_ticker(ticker):
                print(f'⏸ {ticker}: marked stengt - hopper over')
                continue
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

            if PAPER_TRADING_ENABLED:
                risk_ok, risk_msg = apply_risk_exits(ticker, price)
                if risk_ok:
                    # DUPLICATE_ALERT_GUARD
                    # direct pushover disabled unless trade executed
                    # send_pushover_alert(f"🛑 {risk_msg}\nPris: {price:.2f}", title="Risk Exit")

            if confidence >= MIN_CONFIDENCE and signal in ["BUY", "SELL / AVOID"]:
                candidates.append({
                    "ticker": ticker,
                    "price": price,
                    "decision": decision,
                    "signal": signal,
                    "confidence": confidence,
                    "score": float(decision.get("decision_score", 0) or 0),
                    "rsi": result.get("rsi"),
                })

            time.sleep(SCAN_SLEEP_SECONDS)

        except Exception as e:
            print(f"Feil på {ticker}: {e}")

    candidates = sorted(candidates, key=lambda x: (x["confidence"], x["score"]), reverse=True)[:3]

    if PAPER_TRADING_ENABLED:
        for c in candidates:
            if c["signal"] == "BUY" and should_buy(c["decision"], 50, rules):
                ok, msg = paper_buy(c["ticker"], c["price"], c["decision"])
                if ok:
                    alert_ok, alert_reason = should_send_alert(c["ticker"], c["signal"])
                    if alert_ok:
                        # DUPLICATE_ALERT_GUARD
                    # direct pushover disabled unless trade executed
                    # send_pushover_alert(
                            f"🧪 {msg}\nPris: {c['price']:.2f}\nConfidence: {c['confidence']}%",
                            title="Top 3 Paper Trading"
                        )
                        record_alert(c["ticker"], c["signal"], {"confidence": c["confidence"], "price": c["price"], "reason": alert_reason})
                    else:
                        print(f"🔕 {c['ticker']}: alert blokkert ({alert_reason})")
            elif c["signal"] == "SELL / AVOID":
                ok, msg = paper_sell(c["ticker"], c["price"], c["decision"])
                if ok:
                    alert_ok, alert_reason = should_send_alert(c["ticker"], c["signal"])
                    if alert_ok:
                        # DUPLICATE_ALERT_GUARD
                    # direct pushover disabled unless trade executed
                    # send_pushover_alert(
                            f"🧪 {msg}\nPris: {c['price']:.2f}\nConfidence: {c['confidence']}%",
                            title="Top 3 Paper Trading"
                        )
                        record_alert(c["ticker"], c["signal"], {"confidence": c["confidence"], "price": c["price"], "reason": alert_reason})
                    else:
                        print(f"🔕 {c['ticker']}: alert blokkert ({alert_reason})")

    if PAPER_TRADING_ENABLED:
        for c in candidates:
            ok, msg = auto_trade(c["ticker"], c["price"], c["decision"], rsi=c.get("rsi"))
            print(f"Auto trade {c['ticker']}: {msg}")
            if ok:
                # DUPLICATE_ALERT_GUARD
                    # direct pushover disabled unless trade executed
                    # send_pushover_alert(f"🧪 {msg}\nPris: {c['price']:.2f}\nConfidence: {c['confidence']}%", title="Auto Paper Trading")

    portfolio = load_portfolio()
    value = portfolio_value(portfolio, latest_prices)
    stats = performance_stats(portfolio, latest_prices)
    print(f"Portfolio value: {value}")
    print(f"Performance: {stats}")
    return value


if __name__ == "__main__":
    run_once()
