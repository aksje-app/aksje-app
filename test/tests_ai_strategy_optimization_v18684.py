from ai_strategy_optimization import _metrics, build_optimization_analysis


def _portfolio(n=30):
    trades=[]
    for i in range(n):
        ticker=f"T{i}"
        confidence=60 + (i % 35)
        entry=100.0
        exit_price=110.0 if i % 3 else 95.0
        trades.append({"type":"BUY","ticker":ticker,"price":entry,"time":f"2025-01-{(i%28)+1:02d}T10:00:00","confidence":confidence,"reason":"Momentum" if i%2 else "Value","market":"USA","sector":"Tech"})
        trades.append({"type":"SELL","ticker":ticker,"price":exit_price,"time":f"2025-02-{(i%28)+1:02d}T10:00:00","reason":"Trailing Stop" if i%2 else "Target","rule_used":"Trailing Stop" if i%2 else "Target"})
    return {"trades":trades}


def test_metrics():
    m=_metrics([10,-5,8])
    assert m["observations"] == 3
    assert m["hit_rate_pct"] > 60


def test_insufficient_data_has_no_proposals():
    r=build_optimization_analysis({"trades":[]})
    assert r["data_sufficient"] is False
    assert r["proposals"] == []


def test_sufficient_data_builds_advisory_proposals():
    r=build_optimization_analysis(_portfolio())
    assert r["data_sufficient"] is True
    assert r["mode"]["automatic_activation"] == "OFF"
    assert len(r["proposals"]) >= 1
