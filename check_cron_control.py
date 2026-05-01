
from cron_control import cron_status_text, should_run_background_scan

print("Cron control status:")
print(cron_status_text())

allowed, reason = should_run_background_scan()
print("allowed:", allowed)
print("reason:", reason)
