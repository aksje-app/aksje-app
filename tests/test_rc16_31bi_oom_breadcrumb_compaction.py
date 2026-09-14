from __future__ import annotations

import json
from pathlib import Path


def test_runtime_breadcrumb_payload_is_bounded(monkeypatch):
    import runtime_breadcrumbs as rb

    class Storage:
        def __init__(self): self.latest=None; self.events=[]
        def write_json(self, name, payload): self.latest=(name,payload); return True
        def append_jsonl(self, name, payload): self.events.append((name,payload)); return True
    storage=Storage()
    import services.storage_service as ss
    monkeypatch.setattr(ss, "get_storage_service", lambda: storage)
    payload=rb.mark_breadcrumb("unit:test", component="pytest", detail={"huge": "x"*10000, "rows": list(range(1000))})
    assert payload["persisted"] is True
    assert storage.latest[0] == rb.LATEST_KEY
    encoded=json.dumps(storage.latest[1])
    assert len(encoded) < 10000
    assert len(storage.latest[1]["detail"]["huge"]) <= 300


def test_status_chain_compaction_removes_heavy_trees():
    import manual_job_background as mb
    chain={
        "chain_id":"C1", "status":"OK", "source_run_id":"R1",
        "stages":[{"name":"AUTONOMOUS","status":"OK","detail":{"blob":"x"*100000}}],
        "learning_portfolio":{"last_run_id":"R1","status":"ACTIVE","positions":{"A":{},"B":{}},"closed_positions":[{},{}]},
        "learning_decisions":[{"blob":"x"*10000} for _ in range(200)],
        "learning_trades":[{"x":1}],
        "autonomy_cycle":{"run_id":"R1","decisions":[1,2],"trades":[1]},
        "autonomy_learning_account":{"status":"OK","decisions":[1,2,3]},
        "autonomy_core":{"blob":"x"*1000000},
    }
    compact=mb._compact_chain_for_status(chain)
    assert compact["learning_summary"]["decision_count"] == 200
    assert compact["learning_summary"]["open_positions"] == 2
    assert "learning_portfolio" not in compact
    assert "autonomy_core" not in compact
    assert len(json.dumps(compact)) < 20000


def test_bi_source_contains_durable_breadcrumbs_and_diagnostic_export():
    root=Path(__file__).resolve().parents[1]
    scheduler=(root/"scheduled_runner.py").read_text()
    market=(root/"market_intelligence.py").read_text()
    manual=(root/"manual_job_background.py").read_text()
    assert 'mark_breadcrumb("scheduler:due_jobs:run_scheduler_cycle:before"' in scheduler
    assert 'mark_breadcrumb(f"report:{phase}:{completed}/{total}"' in market
    assert 'report:autonomy:execute_market_mission:before' in market
    assert 'report:pdf:main:before' in market
    assert 'runtime/OOM_BREADCRUMB_LATEST.json' in manual
