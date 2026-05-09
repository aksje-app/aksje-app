from macro_rates_breadth_engine import analyze_macro_rates_breadth, macro_adjustment_for_forecast

spy = [100 + i * 0.2 for i in range(150)]
qqq = [100 + i * 0.25 for i in range(150)]
iwm = [100 + i * 0.1 for i in range(150)]
dia = [100 + i * 0.15 for i in range(150)]
tnx = [40 - i * 0.02 for i in range(150)]
dollar = [100 - i * 0.01 for i in range(150)]
oil = [70 + i * 0.01 for i in range(150)]
vix = [16 for _ in range(150)]

result = analyze_macro_rates_breadth(
    spy_prices=spy, qqq_prices=qqq, iwm_prices=iwm, dia_prices=dia,
    tnx_prices=tnx, dollar_prices=dollar, oil_prices=oil, vix_prices=vix
)
assert 0 <= result.combined_score <= 100
assert 0 <= result.risk_score <= 100
adj = macro_adjustment_for_forecast(result)
assert "market_regime_bias" in adj
assert "confidence_adjustment" in adj

print("macro_rates_breadth_engine smoke test OK")
