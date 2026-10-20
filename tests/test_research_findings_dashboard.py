from hashlib import sha256
from research_findings_dashboard import collect

class Storage:
    def __init__(self, values):
        self.values = values
    def read_json(self, key, fallback):
        return self.values.get(key, fallback)

def test_research_findings_use_persisted_evidence():
    ticker = "TEST"
    path = "strategy_history/optimized/AUTONOMY/" + sha256(ticker.encode()).hexdigest() + ".json"
    result = {"status": "COMPLETE_RESEARCH", "finalists": [
        {"stop_pct": 4.0, "hold_sessions": 20,
         "validation": {"total_pct": 3.0},
         "holdout": {"total_pct": -2.0, "trades": 2}}
    ]}
    data = collect(Storage({
        "strategy_history/optimization_progress.json": {
            "completed_tickers": [ticker], "total": 1970, "processed": 1},
        path: result
    }), "AUTONOMY")
    assert data["complete"] == 1
    assert data["counts"][(4.0, 20)] == 1
    assert data["validation"] == [3.0]
    assert data["holdout"] == [-2.0]

def test_missing_results_are_not_invented():
    data = collect(Storage({
        "strategy_history/optimization_progress.json": {
            "completed_tickers": ["MISSING"], "processed": 1, "total": 1970}
    }), "SUPER_PORTFOLIO")
    assert data["complete"] == 0
    assert data["missing_records"] == 1
    assert not data["counts"]
