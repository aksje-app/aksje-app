from strategy_history_progress_view import snapshot
class Fake:
    def read_json(self, name, default=None):
        return {"status":"RUNNING","total":2010,"completed":237,"rejected":3,"updated_at":"2026-10-19T20:17:16Z"}
def test_live_progress():
    x=snapshot(Fake())
    assert x["done"]==237 and x["rejected"]==3 and x["total"]==2010
    assert round(x["pct"],1)==11.8
    assert round(x["processed_pct"],1)==11.9
def test_unavailable_progress():
    class Empty:
        def read_json(self, name, default=None): return {}
    assert snapshot(Empty())["pct"] is None
