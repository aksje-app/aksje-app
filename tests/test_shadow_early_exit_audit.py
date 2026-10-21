from shadow_early_exit_audit import audit_closed_shadow_trades

def test_same_day_next_day_and_no_invented_costs():
    r=audit_closed_shadow_trades([
        {"symbol":"DNO.OL","holding_days":0.5,"entry_price":22.42,"exit_price":22.30},
        {"symbol":"BWE.OL","holding_days":1,"entry_price":69,"exit_price":67.20,"total_cost_pct":0.2},
        {"symbol":"OMC.OL","holding_days":0,"entry_price":39.6,"exit_price":38.5,"total_cost_pct":0.1},
    ])
    assert r["read_only"] is True
    assert r["summary"]["same_day"]["count"]==2
    assert r["summary"]["next_day"]["count"]==1
    assert r["summary"]["same_day"]["net_sample"]==1
    assert r["missing"]["costs"]==1
    assert r["summary"]["next_day"]["net_mean_pct"] < -2

def test_missing_prices_are_not_estimated():
    r=audit_closed_shadow_trades([{"holding_days":1,"entry_price":100}])
    assert r["missing"]["prices"]==1
    assert not r["rows"]
