from forecast_engine import build_forecast, build_all_horizons

prices = [
    100, 101, 100.5, 102, 103, 103.5, 104, 103.8, 105, 106,
    106.5, 107, 108, 107.5, 109, 110, 111, 110.5, 112, 113,
    114, 113.5, 115, 116, 117, 118, 117.2, 119, 120, 121,
    122, 121.5, 123, 124, 125, 126, 125.5, 127, 128, 129
]

result = build_forecast("TEST", prices, "1m", ai_score=68, sentiment_score=0.25)
assert result.summary.ticker == "TEST"
assert result.summary.horizon == "1m"
assert result.summary.current_price == 129
assert len(result.points) == result.summary.days + 1
assert result.summary.bull_price >= result.summary.base_price >= result.summary.bear_price
assert 0 <= result.summary.confidence <= 100
assert 0 <= result.summary.forecast_strength <= 100
assert result.summary.forecast_strength_label

all_results = build_all_horizons("TEST", prices, ai_score=68, sentiment_score=0.25)
assert set(all_results.keys()) == {"1d", "1w", "1m", "3m", "6m"}

print("forecast_engine smoke test OK")
