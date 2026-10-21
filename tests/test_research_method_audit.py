from hashlib import sha256
from research_findings_dashboard import collect

class Store:
    def __init__(self, records): self.records=records
    def read_json(self, key, default): return self.records.get(key, default)

def test_audit_pairs_same_finalist_and_tracks_insufficient_history():
    ticker="ABC"
    digest=sha256(ticker.encode()).hexdigest()
    record={"status":"COMPLETE_RESEARCH","finalists":[
        {"stop_pct":6,"hold_sessions":20,
         "validation":{"total_pct":-15,"trades":4},
         "holdout":{"total_pct":65,"trades":2}},
        {"stop_pct":7,"hold_sessions":30,
         "validation":{"total_pct":1,"trades":1},
         "holdout":None}]}
    state={"completed_tickers":[ticker,"DEF"],"processed":2,"total":1970}
    records={"strategy_history/optimization_progress.json":state,
       "strategy_history/optimized/AUTONOMY/"+digest+".json":record,
       "strategy_history/optimized/AUTONOMY/"+sha256(b"DEF").hexdigest()+".json":{"status":"INSUFFICIENT_HISTORY"}}
    data=collect(Store(records),"AUTONOMY")
    assert data["complete"]==1
    assert data["incomplete_history"]==1
    assert data["missing_records"]==0
    assert data["paired"]==[(-15.,65.,4,2)]
    assert data["zero_holdout_trades"]==1
