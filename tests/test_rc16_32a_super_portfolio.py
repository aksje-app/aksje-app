from super_portfolio import SuperPortfolioConfig, rank_candidates, target_weights, _stop_status


def _c(ticker,score,risk,price,sector="Industrials"):
    return {"ticker":ticker,"investment_score":score,"risk_score":risk,"data_quality_score":90,"price":price,"sector":sector,"market":"Norge"}


def test_ranking_and_weights_are_risk_adjusted_and_sum_to_100():
    cfg=SuperPortfolioConfig(target_positions=3,max_position_pct=50)
    ranked=rank_candidates([_c("AAA",90,20,100),_c("BBB",88,60,100),_c("CCC",82,30,100)],cfg)
    weights=target_weights(ranked,cfg)
    assert list(weights)==["AAA","BBB","CCC"]
    assert abs(sum(weights.values())-100)<0.05
    assert weights["AAA"] > weights["BBB"]


def test_stop_watch_levels_follow_current_three_percent_cap():
    cfg=SuperPortfolioConfig()
    p={"entry_price":100,"peak_price":120,"last_price":118}
    out=_stop_status(p,cfg)
    assert out["stop_status"]=="WATCH"
    assert out["hard_stop_drawdown_pct"]==3.0
    p["last_price"]=117.2
    assert _stop_status(p,cfg)["stop_status"]=="NEAR STOP"
    p["last_price"]=116.39
    assert _stop_status(p,cfg)["stop_status"]=="STOP TRIGGERED"
