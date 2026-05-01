
from notifier import pushover_enabled, send_pushover_alert

print("pushover_enabled:", pushover_enabled())
ok, err = send_pushover_alert("Test fra Render Shell / check_pushover.py", title="Pushover test")
print("sent:", ok)
print("error:", err)
