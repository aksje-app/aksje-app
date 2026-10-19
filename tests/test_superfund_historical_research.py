from superfund_historical_research import test_item
def test_insufficient_history_is_not_backfilled():
    assert test_item({"observations":[{"price_at":"2026-10-01","price":100}]}) == {}
def test_true_observations_enable_grid():
    item={"observations":[{"price_at":f"2026-10-{i:02}","price":100+i} for i in range(1,25)]}
    assert len(test_item(item))==12
