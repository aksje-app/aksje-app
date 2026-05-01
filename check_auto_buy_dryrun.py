
from scanner_worker import get_watchlist, analyze_ticker
from settings_store import load_settings
from market_hours import open_markets

settings = load_settings()
print("=== AUTO BUY DRY RUN ===")
print("Open markets:", open_markets())
print("Settings:")
for k in ["auto_trading_enabled", "background_scanning_enabled", "min_buy_score", "min_buy_confidence", "max_open_positions", "max_tickers_per_market", "scan_top_picks_only"]:
    print(f"- {k}: {settings.get(k)}")

tickers = get_watchlist()
print("Watchlist:", tickers)

buy_candidates = []
for ticker in tickers:
    try:
        result = analyze_ticker(ticker)
        if not result:
            print(f"{ticker}: ingen analyse")
            continue

        print(
            f"{ticker}: {result['signal']} | score={result['score']:.2f} | "
            f"conf={result['confidence']} | price={result['price']:.2f} | "
            f"ctx={result.get('technical_context', {})}"
        )

        if "BUY" in str(result["signal"]).upper():
            buy_candidates.append(result)
    except Exception as e:
        print(f"{ticker}: FEIL {type(e).__name__}: {e}")

print("BUY candidates:", [(x["ticker"], x["score"], x["confidence"]) for x in buy_candidates])
print("========================")
