from superfund_history_progress_view import snapshot
def test_fund_metrics():
    x=snapshot({"coverage":{"listings":3188,"fresh_prices":3188,"source_totals":{"fond":917,"etf":2271},"history_points_cap_per_listing":60},"prior_learning":{"paired_dates":0,"minimum_dates":80,"status":"WAITING_FOR_VERIFIED_REFERENCE"}})
    assert x["listings"]==3188 and x["paired"]==0 and x["history_cap"]==60
def test_missing():
    assert snapshot({})["listings"]==0
