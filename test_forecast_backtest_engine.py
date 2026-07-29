from forecast_backtest_engine import run_backtest_learning_batch, summarize_backtest_learning

# No log required: should safely return result shape.
result = run_backtest_learning_batch({"TEST": [100+i for i in range(200)]}, max_evaluations=5)
assert "evaluated_count" in result
assert "skipped_count" in result
assert "learning_stats" in result

summary = summarize_backtest_learning()
assert "global" in summary
assert "horizons" in summary
assert "best_tickers" in summary

print("forecast_backtest_engine smoke test OK")
