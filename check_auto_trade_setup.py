
from settings_store import load_settings
from cron_control import cron_status_text, should_run_background_scan
from market_hours import market_status_lines, open_markets
from notifier import pushover_enabled

settings = load_settings()
allowed, reason = should_run_background_scan()

print("=== AUTO TRADE SETUP ===")
print("Cron allowed:", allowed, "|", reason)
print("Pushover enabled:", pushover_enabled())
print("Auto trading enabled:", settings.get("auto_trading_enabled"))
print("Background scanning enabled:", settings.get("background_scanning_enabled"))
print("Vacation/full stop:", settings.get("vacation_mode_enabled"), settings.get("full_stop_reason"))
print("Min score:", settings.get("min_buy_score"))
print("Min confidence:", settings.get("min_buy_confidence"))
print("Max positions:", settings.get("max_open_positions"))
print("Interval minutes:", settings.get("scan_interval_minutes"))
print("Pause until:", settings.get("pause_scanning_until"))
print("Open markets:", open_markets())
for line in market_status_lines():
    print("-", line)
print("========================")
