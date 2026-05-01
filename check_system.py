import importlib
import inspect
import traceback
from pathlib import Path

print("=== AKSJE APP SYSTEM CHECK ===")

failures = []

def check(name, func):
    print(f"\n--- {name} ---")
    try:
        result = func()
        if result is not None:
            print(result)
        print("OK")
    except Exception as e:
        failures.append((name, type(e).__name__, str(e)))
        print("ERROR:", type(e).__name__, e)
        traceback.print_exc(limit=2)

def check_compile_app():
    compile(Path("app.py").read_text(encoding="utf-8"), "app.py", "exec")
    print("app.py compiles")

def check_imports():
    modules = [
        "settings_store",
        "trading_settings",
        "market_hours",
        "background_guard",
        "cron_control",
        "market_selector",
        "insider",
        "signal_engine",
        "paper_store",
        "paper_trading",
        "trading_engine",
        "scanner_worker",
        "notifier",
        "auth",
        "user_store",
    ]
    for m in modules:
        importlib.import_module(m)
        print("import", m, "OK")

def check_settings():
    from settings_store import load_settings
    s = load_settings()
    for k in [
        "background_scanning_enabled",
        "scan_interval_minutes",
        "pause_scanning_until",
        "last_scan_at",
        "latest_buy_now_candidates",
    ]:
        print(k, "=", s.get(k))

def check_market():
    from market_hours import market_status_lines, open_markets
    for line in market_status_lines():
        print(line)
    print("open_markets:", open_markets())

def check_cron():
    from cron_control import cron_status_text, should_run_background_scan
    print(cron_status_text())
    print("should_run:", should_run_background_scan())

def check_insider():
    from insider import get_insider_data, get_insider_signal, get_insider_transactions
    d = get_insider_data("AAPL")
    print("get_insider_data OK, keys:", sorted(list(d.keys()))[:12])
    print("signal score:", d.get("score"))
    print("tx count:", len(get_insider_transactions("AAPL") or []))

def check_paper():
    from paper_store import load_portfolio
    p = load_portfolio()
    print("cash:", p.get("cash"))
    print("positions:", list((p.get("positions") or {}).keys()))
    print("trades:", len(p.get("trades", [])))

def check_notifier():
    from notifier import pushover_enabled
    print("pushover_enabled:", pushover_enabled())

def check_market_selector_signature():
    from market_selector import auto_rank_market
    sig = str(inspect.signature(auto_rank_market))
    print("auto_rank_market signature:", sig)
    assert "force_manual_fetch" in sig

def check_auto_buy_dry():
    from scanner_worker import get_watchlist, analyze_ticker
    tickers = get_watchlist()[:3]
    print("watchlist sample:", tickers)
    for t in tickers:
        r = analyze_ticker(t)
        if r:
            print(t, r.get("signal"), r.get("score"), r.get("confidence"))
        else:
            print(t, "no result")

check("Compile app.py", check_compile_app)
check("Imports", check_imports)
check("Settings", check_settings)
check("Market calendar", check_market)
check("Cron control", check_cron)
check("Insider compatibility", check_insider)
check("Paper portfolio", check_paper)
check("Notifier", check_notifier)
check("Market selector signature", check_market_selector_signature)
check("Auto-buy dry sample", check_auto_buy_dry)

print("\n=== RESULT ===")
if failures:
    print("FAILURES:")
    for f in failures:
        print("-", f)
    raise SystemExit(1)

print("ALL CHECKS PASSED")
