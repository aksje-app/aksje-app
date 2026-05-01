
from stop_control import full_stop_status, search_allowed

print("Full stop status:")
print(full_stop_status())

allowed, reason = search_allowed()
print("search_allowed:", allowed)
print("reason:", reason)
