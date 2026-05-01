
def _ticker_market(ticker):
    t = str(ticker).upper()
    if t.endswith(".OL"):
        return "NORGE"
    if t.endswith(".ST"):
        return "SVERIGE"
    return "USA"

def _filter_items_by_settings(items, settings):
    allowed = set(enabled_markets(settings))
    max_per = int(settings.get("max_tickers_per_market", 20))
    counts = {"USA": 0, "NORGE": 0, "SVERIGE": 0}
    out = []
    for item in items:
        ticker = item.get("ticker", item if isinstance(item, str) else "")
        market = _ticker_market(ticker)
        if market not in allowed:
            continue
        if counts[market] >= max_per:
            continue
        counts[market] += 1
        out.append(item)
    return out

from settings_store import load_settings, enabled_markets

import os
import time
import requests

from paper_store import force_schema_migration
from paper_trading import auto_trade, load_portfolio, portfolio_value
from alert_state import should_send_alert, record_alert
from market_hours import open_markets, should_process_ticker, market_status_lines

from stocks import get_sp500_tickers, get_norwegian_tickers, get_swedish_tickers
from analysis import score_stock
from signal_engine import build_trading_decision


force_schema_migration()

PAPER_TRADING_ENABLED = os.getenv("PAPER_TRADING_ENABLED", "true").lower() == "true"
SCANNER_MAX_TICKERS = int(os.getenv("SCANNER_MAX_TICKERS", "30"))
SCAN_SLEEP_SECONDS = float(os.getenv("SCAN_SLEEP_SECONDS", "0.2"))


def send_pushover_alert(message, title="Auto Paper Trading"):
    token = os.getenv("PUSHOVER_APP_TOKEN")
    user = os.getenv("PUSHOVER_USER_KEY")

    if not token or not user:
        print("Pushover ikke konfigurert")
        return False

    try:
        res = requests.post(
            "https://api.pushover.net/1/messages.json",
            data={"token": token, "user": user, "title": title, "message": message},
            timeout=15,
        )
        print(f"Pushover status: {res.status_code} {res.text}")
        return res.ok
    except Exception as e:
        print(f"Pushover-feil: {e}")
        return False


def _take(fn, n):
    try:
        return fn(n)
    except TypeError:
        return fn()[:n]


def get_watchlist():
    custom = os.getenv("SCANNER_WATCHLIST", "").strip()
    if custom:
        return [x.strip().upper() for x in custom.replace(";", ",").split(",") if x.strip()]

    markets = open_markets()
    tickers = []

    if "USA" in markets:
        tickers += _take(get_sp500_tickers, 30)
    if "NORGE" in markets:
        tickers += _take(get_norwegian_tickers, 20)
    if "SVERIGE" in markets:
        tickers += _take(get_swedish_tickers, 20)

    out = []
    seen = set()
    for t in tickers:
        if t not in seen:
            seen.add(t)
            out.append(t)

    return out[:SCANNER_MAX_TICKERS]


def get_latest_price(item):
    price = item.get("price")
    if price:
        return float(price)

    hist = item.get("hist")
    if hist is not None and "Close" in hist:
        close = hist["Close"].dropna()
        if len(close) > 0:
            return float(close.iloc[-1])

    return None


def get_rsi_values(item):
    try:
        hist = item.get("hist")
        if hist is not None and "RSI" in hist:
            rsi = hist["RSI"].dropna()
            if len(rsi) >= 2:
                return float(rsi.iloc[-1]), float(rsi.iloc[-2])
            if len(rsi) == 1:
                return float(rsi.iloc[-1]), None
    except Exception:
        pass

    return None, None


def analyze_ticker(ticker):
    item = score_stock(ticker)
    if not item:
        return None

    price = get_latest_price(item)
    if price is None:
        print(f"{ticker}: mangler pris")
        return None

    decision = build_trading_decision(item)
    signal = decision.get("decision", "HOLD / WAIT")
    confidence = int(decision.get("confidence", 0) or 0)
    score = float(decision.get("decision_score", item.get("score", 0)) or 0)
    rsi, prev_rsi = get_rsi_values(item)

    return {
        "ticker": ticker,
        "price": price,
        "item": item,
        "decision": decision,
        "signal": signal,
        "confidence": confidence,
        "score": score,
        "rsi": rsi,
        "prev_rsi": prev_rsi,
    }


def maybe_send_trade_alert(result, msg):
    ticker = result["ticker"]
    signal = result["signal"]

    ok_alert, reason = should_send_alert(ticker, signal)
    if not ok_alert:
        print(f"🔕 {ticker}: trade-varsel blokkert ({reason})")
        return False

    sent = send_pushover_alert(
        f"🧪 {msg}\nPris: {result['price']:.2f}\nConfidence: {result['confidence']}%",
        title="Auto Paper Trading",
    )

    if sent:
        record_alert(
            ticker,
            signal,
            {"price": result["price"], "confidence": result["confidence"], "trade_msg": msg},
        )

    return sent


def run_once():
    for line in market_status_lines():
        print(line)

    markets = open_markets()
    if not markets:
        print("⏸ Alle markeder stengt - ingen scanning")
        return 0

    print(f"Åpne markeder: {markets}")

    tickers = get_watchlist()
    print(f"Scanner {len(tickers)} tickers: {tickers}")

    latest_prices = {}
    trades_executed = 0

    for ticker in tickers:
        try:
            if not should_process_ticker(ticker):
                print(f"⏸ {ticker}: marked stengt")
                continue

            result = analyze_ticker(ticker)
            if result is None:
                continue

            latest_prices[ticker] = result["price"]

            print(
                f"{ticker}: {result['signal']} "
                f"conf={result['confidence']} "
                f"score={result['score']:.2f} "
                f"price={result['price']:.2f}"
            )

            if PAPER_TRADING_ENABLED:
                traded, msg = auto_trade(
                    result["ticker"],
                    result["price"],
                    result["signal"],
                    confidence=result["confidence"],
                    rsi=result.get("rsi"),
                    prev_rsi=result.get("prev_rsi"),
                )
                print(f"Auto trade {ticker}: {msg}")

                if traded:
                    trades_executed += 1
                    maybe_send_trade_alert(result, msg)

            time.sleep(SCAN_SLEEP_SECONDS)

        except Exception as e:
            print(f"Feil på {ticker}: {type(e).__name__}: {e}")

    portfolio = load_portfolio()
    value = portfolio_value(portfolio, latest_prices)
    print(f"Portfolio value: {value}")
    print(f"Cash: {portfolio.get('cash')}")
    print(f"Positions: {list(portfolio.get('positions', {}).keys())}")
    print(f"Trades executed this run: {trades_executed}")

    return trades_executed


if __name__ == "__main__":
    run_once()
