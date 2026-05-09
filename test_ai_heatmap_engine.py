from ai_heatmap_engine import summarize_heatmap, extract_tickers_from_app_state

rows = [
    {"risk_level": "green", "strength": 80, "confidence": 70},
    {"risk_level": "yellow", "strength": 55, "confidence": 55},
    {"risk_level": "red", "strength": 20, "confidence": 30},
]
summary = summarize_heatmap(rows)
assert summary["total"] == 3
assert summary["counts"]["red"] == 1
assert summary["counts"]["yellow"] == 1
assert summary["counts"]["green"] == 1

state = {"portfolio": {"AAPL": {"value": 100}, "MSFT": {"value": 50}}, "watchlist": ["NVDA"]}
tickers = extract_tickers_from_app_state(state)
assert "AAPL" in tickers
assert "MSFT" in tickers
assert "NVDA" in tickers

print("ai_heatmap_engine smoke test OK")


from ai_heatmap_engine import build_matrix_payload, build_sector_treemap_rows, infer_sector_from_ticker

forecast_rows = [
    {"ticker": "AAPL", "horizon": "1m", "strength": 80, "confidence": 70, "bear_pct": -3, "risk_level": "green"},
    {"ticker": "AAPL", "horizon": "3m", "strength": 70, "confidence": 65, "bear_pct": -5, "risk_level": "yellow"},
    {"ticker": "XOM", "horizon": "1m", "strength": 45, "confidence": 50, "bear_pct": -8, "risk_level": "yellow"},
]
payload = build_matrix_payload(forecast_rows)
assert "AAPL" in payload["tickers"]
assert "1m" in payload["horizons"]

sectors = build_sector_treemap_rows(forecast_rows)
assert any(s["sector"] == "Tech / AI" for s in sectors)
assert infer_sector_from_ticker("XOM") == "Energy"
