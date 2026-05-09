from forecast_portfolio import build_portfolio_forecast, normalize_holdings

raw = {
    "AAPL": {"value": 60000},
    "MSFT": {"value": 40000},
}
holdings = normalize_holdings(raw)
assert len(holdings) == 2
assert holdings[0]["ticker"] in {"AAPL", "MSFT"}

prices = {
    "AAPL": [100 + i * 0.2 for i in range(90)],
    "MSFT": [200 + i * 0.15 for i in range(90)],
}
result = build_portfolio_forecast(holdings, prices, horizon="1m")
assert result.total_current == 100000
assert result.total_bull >= result.total_base >= result.total_bear
assert 0 <= result.weighted_strength <= 100
assert len(result.holdings) == 2

print("forecast_portfolio smoke test OK")
