from repositories.application import StrategyDecisionRepository, StrategyRunRepository
from services.storage_service import StorageService
from paper_scanner_runtime import scanner_configuration_snapshot

class RecordingStorage(StorageService):
    def __init__(self, base_dir):
        super().__init__(base_dir=base_dir, database_url="", mode="local")
        self.reads=[]
    def read_json(self, name, default=None):
        self.reads.append(str(name)); return super().read_json(name, default)

def test_strategy_decision_upsert_does_not_read_legacy(tmp_path):
    st=RecordingStorage(tmp_path)
    st.write_json("repositories/strategy_decisions.json", [{"decision_id":"OLD","padding":"x"*10000}])
    st.reads.clear(); repo=StrategyDecisionRepository(st)
    repo.upsert({"decision_id":"NEW","run_id":"R1","evaluated_at":"2026-09-05T00:00:00Z"})
    assert "repositories/strategy_decisions.json" not in st.reads
    assert repo.get("NEW")["decision_id"]=="NEW"

def test_strategy_run_upsert_does_not_read_legacy(tmp_path):
    st=RecordingStorage(tmp_path)
    st.write_json("repositories/strategy_runs.json", [{"strategy_run_id":"OLD","padding":"x"*10000}])
    st.reads.clear(); repo=StrategyRunRepository(st)
    repo.upsert({"strategy_run_id":"NEW","run_id":"R1","completed_at":"2026-09-05T00:00:00Z"})
    assert "repositories/strategy_runs.json" not in st.reads
    assert repo.list(limit=5)[0]["strategy_run_id"]=="NEW"

def test_norway_only_observability(monkeypatch):
    monkeypatch.delenv("PRODUCTION_NORWAY_ONLY", raising=False)
    monkeypatch.setenv("SCANNER_MEMORY_SOFT_LIMIT_MB","1700")
    monkeypatch.delenv("SCHEDULER_MEMORY_SOFT_LIMIT_MB", raising=False)
    cfg=scanner_configuration_snapshot()
    assert cfg["automated_markets"]==["NORGE"]
    assert cfg["production_norway_only"] is True
    assert cfg["scanner_memory_soft_limit_mb"]==1450.0
