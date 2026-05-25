import logging
from cron_control import should_run_background_scan, mark_background_scan_started

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
from paper_trading import auto_trade, paper_buy, load_portfolio, portfolio_value
from alert_state import should_send_alert, record_alert
from market_hours import open_markets, should_process_ticker, market_status_lines
from background_guard import print_market_guard_summary

from stocks import get_sp500_tickers, get_norwegian_tickers, get_swedish_tickers, US_FALLBACK, NORWEGIAN_STOCKS, SWEDISH_STOCKS
from analysis import score_stock
from technical import calculate_rsi, calculate_macd, detect_trend
from patterns import breakout_scanner, detect_head_shoulders, detect_inverse_head_shoulders
from signal_engine import build_trading_decision


force_schema_migration()

PAPER_TRADING_ENABLED = os.getenv("PAPER_TRADING_ENABLED", "true").lower() == "true"
SCANNER_MAX_TICKERS = int(os.getenv("SCANNER_MAX_TICKERS", "30"))
SCAN_SLEEP_SECONDS = float(os.getenv("SCAN_SLEEP_SECONDS", "0.2"))


from notifier import send_pushover_alert  # v18.6.3 centralized notifier


def _take(fn, n):
    try:
        return fn(n)
    except TypeError:
        return fn()[:n]




def _merge_unique(*lists):
    out = []
    seen = set()
    for lst in lists:
        for t in lst or []:
            t = str(t).upper()
            if t and t not in seen:
                seen.add(t)
                out.append(t)
    return out


def build_cron_technical_context(item):
    """
    Samme type teknisk kontekst som Top Picks / Kjøp nå-kortene bruker.
    Dette gjør at Cron og UI vurderer BUY/HOLD/SELL på samme grunnlag.
    """
    try:
        df = item.get("hist")
        if df is None or df.empty or "Close" not in df:
            return {}

        rsi_series = calculate_rsi(df)
        rsi_clean = rsi_series.dropna()
        latest_rsi = float(rsi_clean.iloc[-1]) if len(rsi_clean) else 50.0

        macd, macd_signal, _ = calculate_macd(df)
        macd_clean = macd.dropna()
        signal_clean = macd_signal.dropna()
        latest_macd = float(macd_clean.iloc[-1]) if len(macd_clean) else 0.0
        latest_signal = float(signal_clean.iloc[-1]) if len(signal_clean) else 0.0

        trend_text = str(detect_trend(df))
        if "Opptrend" in trend_text:
            trend = "up"
        elif "Nedtrend" in trend_text:
            trend = "down"
        else:
            trend = "neutral"

        breakout = breakout_scanner(df)
        hs = detect_head_shoulders(df)
        inv = detect_inverse_head_shoulders(df)

        close = df["Close"].dropna()
        recent = close.tail(80)
        if len(recent) > 5:
            low = float(recent.min())
            high = float(recent.max())
            last = float(close.iloc[-1])
            channel_pos = ((last - low) / (high - low) * 100) if high != low else 50
        else:
            channel_pos = 50

        return {
            "rsi": latest_rsi,
            "macd_bullish": latest_macd > latest_signal,
            "breakout_type": breakout.get("type", "neutral"),
            "trend": trend,
            "channel_pos": channel_pos,
            "head_shoulders_found": bool(hs.get("found")),
            "inverse_head_shoulders_found": bool(inv.get("found")),
        }
    except Exception as e:
        print(f"Teknisk context feilet: {e}")
        return {}


def latest_ui_buy_candidate_tickers(settings=None):
    """
    Kjøp nå-listen i UI lagres i settings_store.
    Cron prioriterer disse først, slik at UI og Cron vurderer samme aksjer.
    """
    settings = settings or load_settings()
    out = []
    seen = set()

    for row in settings.get("latest_buy_now_candidates", []) or []:
        ticker = str(row.get("ticker", "")).upper()
        if ticker and ticker not in seen:
            seen.add(ticker)
            out.append(ticker)

    return out

def get_watchlist():
    custom = os.getenv("SCANNER_WATCHLIST", "").strip()
    if custom:
        return [x.strip().upper() for x in custom.replace(";", ",").split(",") if x.strip()]

    settings = load_settings()
    enabled = set(enabled_markets(settings))
    max_per_market = int(settings.get("max_tickers_per_market", 20))
    scan_top_only = bool(settings.get("scan_top_picks_only", True))

    markets = open_markets()
    tickers = []

    # 1) Kandidater som UI nettopp viste som KJØP NÅ prioriteres først.
    ui_candidates = latest_ui_buy_candidate_tickers(settings)
    if ui_candidates:
        print(f"Prioriterer UI Kjøp nå-kandidater: {ui_candidates}")
        tickers += ui_candidates

    # 2) Deretter kjente store/top-picks-kandidater.
    # Før var S&P-listen ofte alfabetisk, og AVGO/NVDA/AMZN kunne komme for sent.
    if "USA" in markets and "USA" in enabled:
        sp = _take(get_sp500_tickers, max(SCANNER_MAX_TICKERS, max_per_market))
        if scan_top_only:
            tickers += _merge_unique(US_FALLBACK, sp)[:max_per_market]
        else:
            tickers += _merge_unique(US_FALLBACK, sp)[:max(SCANNER_MAX_TICKERS, max_per_market)]

    if "NORGE" in markets and "NORGE" in enabled:
        no = _take(get_norwegian_tickers, max_per_market)
        tickers += _merge_unique(NORWEGIAN_STOCKS, no)[:max_per_market]

    if "SVERIGE" in markets and "SVERIGE" in enabled:
        se = _take(get_swedish_tickers, max_per_market)
        tickers += _merge_unique(SWEDISH_STOCKS, se)[:max_per_market]

    out = []
    seen = set()
    for t in tickers:
        if t not in seen:
            seen.add(t)
            out.append(t)

    # Åpne posisjoner må alltid overvåkes for stop-loss/take-profit/trailing.
    current_positions = list(load_portfolio().get("positions", {}).keys())
    for t in current_positions:
        t = str(t).upper()
        if t not in seen:
            seen.add(t)
            out.append(t)

    return out[:max(SCANNER_MAX_TICKERS, len(current_positions), max_per_market)]



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
    except Exception as e:
        logging.warning("Silenced exception restored in v18.6.3: %s", e)

    return None, None


def analyze_ticker(ticker):
    item = score_stock(ticker, use_news=False)
    if not item:
        return None

    price = get_latest_price(item)
    if price is None:
        print(f"{ticker}: mangler pris")
        return None

    technical_context = build_cron_technical_context(item)
    decision = build_trading_decision(item, technical_context)

    signal = decision.get("decision", "HOLD / WAIT")
    confidence = int(decision.get("confidence", 0) or 0)
    score = float(decision.get("decision_score", decision.get("final_score", item.get("score", 0))) or 0)
    rsi, prev_rsi = get_rsi_values(item)

    # Fallback: bruk RSI fra context dersom hist ikke har egen RSI-kolonne.
    if rsi is None:
        rsi = technical_context.get("rsi")

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
        "technical_context": technical_context,
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


def run_once(force=False):
    if force:
        print("Cron control: FORCE=true, kjører auto-motor nå")
    else:
        _allowed, _reason = should_run_background_scan()
        print(f"Cron control: {_reason}")
        if not _allowed:
            print("⏸ Cron våknet, men scanner ikke nå.")
            return 0
        mark_background_scan_started()

    print_market_guard_summary()
    for line in market_status_lines():
        print(line)

    markets = open_markets()
    if not markets:
        print("⏸ Alle markeder stengt - ingen scanning")
        return 0

    print(f"Åpne markeder: {markets}")
    settings = load_settings()
    auto_trading_enabled = bool(settings.get("auto_trading_enabled", False))
    if bool(settings.get("auto_trading_paused", False)):
        auto_trading_enabled = False
        print("⏸ Auto trading er pauset i app-innstillinger")
    if bool(settings.get("auto_trading_emergency_stop", False)):
        auto_trading_enabled = False
        print("🧯 Auto trading er i NØDSTOPP - ingen nye handler")
    min_buy_score = float(settings.get("min_buy_score", 7.2))
    min_buy_confidence = int(settings.get("min_buy_confidence", 70))
    if not auto_trading_enabled:
        print("⏸ Auto trading er deaktivert i app-innstillinger")

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

            if PAPER_TRADING_ENABLED and auto_trading_enabled:
                signal_text = str(result["signal"]).upper()
                allow_trade = True
                open_positions = (load_portfolio() or {}).get("positions", {}) or {}
                has_existing_position = str(result["ticker"]).upper() in {str(t).upper() for t in open_positions.keys()}

                if has_existing_position:
                    traded, msg = auto_trade(
                        result["ticker"],
                        result["price"],
                        result["signal"],
                        confidence=result["confidence"],
                        rsi=result.get("rsi"),
                        prev_rsi=result.get("prev_rsi"),
                    )
                    print(f"Auto risk check {ticker}: {msg}")

                    if traded:
                        trades_executed += 1
                        print("Trade-varsling hÃ¥ndteres av trading_engine")
                    continue

                if "BUY" in signal_text:
                    if result["score"] < min_buy_score:
                        print(f"⏸ {ticker}: BUY blokkert - score {result['score']:.2f} < min {min_buy_score}")
                        allow_trade = False
                    elif result["confidence"] < min_buy_confidence:
                        print(f"⏸ {ticker}: BUY blokkert - confidence {result['confidence']} < min {min_buy_confidence}")
                        allow_trade = False

                    if allow_trade:
                        print(f"✅ {ticker}: BUY-kandidat godkjent, prøver paper_buy direkte")
                        traded, msg = paper_buy(
                            result["ticker"],
                            result["price"],
                            result["confidence"],
                            "AUTO BUY via Cron/Kjøp nå"
                        )
                        print(f"Auto BUY {ticker}: {msg}")

                        if traded:
                            trades_executed += 1
                            print("Trade-varsling håndteres av trading_engine")
                    else:
                        print(f"Auto BUY {ticker}: blokkert av regler")

                else:
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
                        print("Trade-varsling håndteres av trading_engine")

            elif not PAPER_TRADING_ENABLED:
                print("⏸ PAPER_TRADING_ENABLED=false i Render env")

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
