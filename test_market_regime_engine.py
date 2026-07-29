from market_regime_engine import detect_market_regime, regime_to_forecast_inputs

spy = [100 + i * 0.2 for i in range(150)]
qqq = [100 + i * 0.25 for i in range(150)]
vix = [16 for _ in range(100)]

result = detect_market_regime(spy, qqq, vix)
assert result.regime in {"bull", "neutral", "bear", "stress"}
assert 0 <= result.score <= 100
assert 0 <= result.confidence <= 100

mapped = regime_to_forecast_inputs(result)
assert mapped["market_regime"] in {"neutral", "bull", "bear", "volatile"}
assert "event_risk" in mapped

stress_spy = [150 - i * 0.8 for i in range(150)]
stress_vix = [40 for _ in range(100)]
stress = detect_market_regime(stress_spy, stress_spy, stress_vix)
assert stress.regime in {"stress", "bear"}

print("market_regime_engine smoke test OK")
