
from settings_store import load_settings
from cron_control import should_run_background_scan
from market_hours import open_markets, market_status_lines
from scanner_worker import get_watchlist, analyze_ticker
from paper_store import load_portfolio
from trading_settings import load_rules

settings = load_settings()
rules = load_rules()
portfolio = load_portfolio()
allowed, reason = should_run_background_scan()

print("=== AUTO BUY PERMANENT CHECK ===")
print("Cron allowed:", allowed, "|", reason)
print("Open markets:", open_markets())
for line in market_status_lines():
    print("-", line)

print("\nSettings:")
for k in [
    "auto_trading_enabled",
    "background_scanning_enabled",
    "vacation_mode_enabled",
    "pause_scanning_until",
    "last_scan_at",
    "scan_interval_minutes",
    "latest_buy_now_candidates",
]:
    print(f"- {k}: {settings.get(k)}")

print("\nTrading rules:")
for k in ["min_buy_score", "min_buy_confidence", "max_buy_rsi", "max_open_positions", "max_trades_per_day", "position_size_pct"]:
    print(f"- {k}: {rules.get(k)}")

print("\nPortfolio:")
print("cash:", portfolio.get("cash"))
print("positions:", list(portfolio.get("positions", {}).keys()))
print("trades today / total:", len(portfolio.get("trades", [])), "total trades logged")

tickers = get_watchlist()
print("\nWatchlist:", tickers)

buy_candidates = []
for ticker in tickers:
    try:
        r = analyze_ticker(ticker)
        if not r:
            print(f"{ticker}: no result")
            continue
        decision = r.get("decision", {})
        print(
            f"{ticker}: signal={r['signal']} score={r['score']:.2f} "
            f"conf={r['confidence']} price={r['price']:.2f} "
            f"risk={decision.get('risk')} reasons={decision.get('reasons', [])[:1]} warnings={decision.get('warnings', [])[:1]}"
        )
        if "BUY" in str(r["signal"]).upper():
            buy_candidates.append(r)
    except Exception as e:
        print(f"{ticker}: ERROR {type(e).__name__}: {e}")

print("\nBUY candidates:", [(x["ticker"], x["score"], x["confidence"]) for x in buy_candidates])
print("================================")
