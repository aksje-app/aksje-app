from autonomy_trade_diagnosis import diagnose

def test_loss_diagnosis_never_claims_causal_backtest():
    rows=[{"action":"BUY","ticker":"AAA"},{"action":"SELL","reason":"STOP_LOSS: test","pnl":-50,"holding_days":2},
          {"action":"SELL_PARTIAL","reason":"PROFIT_PROTECT","pnl":20,"holding_days":5}]
    d=diagnose(rows)
    assert d["reasons"]["STOP_LOSS"]["pnl"] == -50
    assert d["reasons"]["PROFIT_PROTECT"]["pnl"] == 20
    assert d["missing_technical_timing"] == 1
    assert d["counterfactual_validated"] is False
