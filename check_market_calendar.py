
from market_hours import market_status_lines, open_markets

print("Børsstatus:")
for line in market_status_lines():
    print("-", line)

print("Åpne markeder:", open_markets())
