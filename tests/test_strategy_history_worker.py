from strategy_history_worker import simulate, STOPS, HOLDS

def test_grid_dimensions():
    assert len(STOPS) * len(HOLDS) == 16

def test_next_open_and_gap_stop():
    rows = [{"date":str(i),"open":100.0,"low":100.0,"close":100.0} for i in range(10)]
    rows[1]["open"] = 110.0
    rows[2].update(open=98.0,low=97.0,close=99.0)
    assert simulate(rows, 5.0, 5)[0] < -10

def test_insufficient_history():
    assert simulate([{"open":100,"close":100}], 5, 5) == []
