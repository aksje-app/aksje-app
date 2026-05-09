from forecast_store import (
    build_and_store_all_horizons,
    compute_alerts,
    evaluate_forecast_accuracy,
    load_latest_forecast,
)

prices = [100 + i * 0.5 for i in range(80)]
payload = build_and_store_all_horizons("TESTX", prices, ai_score=65, sentiment_score=0.2)
assert payload["ticker"] == "TESTX"
assert "1m" in payload["horizons"]

latest = load_latest_forecast("TESTX")
assert latest is not None
assert latest["ticker"] == "TESTX"

eval_row = evaluate_forecast_accuracy(payload, actual_price=145, horizon="1m")
assert eval_row["ticker"] == "TESTX"
assert "error_pct" in eval_row

alerts = compute_alerts(payload)
assert isinstance(alerts, list)

print("forecast_store smoke test OK")


from forecast_store import get_forecast_vs_actual_series

series = get_forecast_vs_actual_series(payload, prices[:22], "1m")
assert series["ticker"] == "TESTX"
assert series["horizon"] == "1m"
assert len(series["base"]) > 0
assert "evaluation" in series


from forecast_store import compute_intelligent_alerts, summarize_alerts

smart_alerts = compute_intelligent_alerts(payload)
assert isinstance(smart_alerts, list)
summary_alerts = summarize_alerts(smart_alerts)
assert "counts" in summary_alerts
assert "top_level" in summary_alerts
