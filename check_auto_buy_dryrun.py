
from scanner_worker import get_watchlist, analyze_ticker
from market_hours import open_markets
from settings_store import load_settings
from stop_control import search_allowed
from cron_control import should_run_background_scan

print("settings:", load_settings())
print("search_allowed:", search_allowed())
print("cron_allowed:", should_run_background_scan())
print("open_markets:", open_markets())

tickers = get_watchlist()[:20]
print("watchlist:", tickers)

for ticker in tickers:
    result = analyze_ticker(ticker)
    if not result:
        print(ticker, "NO RESULT")
        continue
    print(
        ticker,
        "signal=", result["signal"],
        "conf=", result["confidence"],
        "score=", result["score"],
        "price=", result["price"],
        "rsi=", result.get("rsi"),
    )
