
from background_guard import print_market_guard_summary, market_guard_summary
from stocks import get_sp500_tickers

print_market_guard_summary()

sample = get_sp500_tickers(5)
print("Sample:", sample)
print("Summary:", market_guard_summary(sample))
