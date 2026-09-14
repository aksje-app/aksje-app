from __future__ import annotations

from types import SimpleNamespace

import scheduled_runner as runner
import storage_retention as retention


def test_retention_parses_render_true_and_exposes_raw_value(monkeypatch):
    monkeypatch.setenv("STORAGE_RETENTION_APPLY", "True")
    monkeypatch.setenv("STORAGE_RETENTION_BATCH_SIZE", "20")
    monkeypatch.setenv("STORAGE_RETENTION_TIME_BUDGET_SECONDS", "45")
    config = retention.retention_configuration()
    assert config["raw_apply_env"] == "True"
    assert config["normalized_apply_env"] == "true"
    assert config["parsed_apply_enabled"] is True
    assert config["batch_size"] == 20
    assert config["time_budget_seconds"] == 45.0


def test_retention_applies_immediately_and_stays_bounded(monkeypatch):
    class FakeStorage:
        def __init__(self):
            self.deleted = []
        def health(self):
            return SimpleNamespace(to_dict=lambda: {"ok": True, "backend": "postgres"})
        def storage_usage_report(self):
            return {
                "database_bytes": 1000,
                "capacity_bytes": 5000,
                "largest_kv_documents": [
                    {"name": "repositories/strategy_decisions.json", "payload_bytes": 100_000_000},
                    {"name": "repositories/market_snapshots.json", "payload_bytes": 90_000_000},
                ],
            }
        def list_json_names(self):
            return [f"operations/run_traces/{i:03d}.json" for i in range(230)]
        def list_jsonl_names(self):
            return []
        def delete_json(self, name):
            self.deleted.append(name)
            return True

    fake = FakeStorage()
    monkeypatch.setenv("DATABASE_URL", "postgres://example")
    monkeypatch.setenv("STORAGE_RETENTION_APPLY", "True")
    monkeypatch.setenv("STORAGE_RETENTION_BATCH_SIZE", "7")
    monkeypatch.setattr(retention, "get_storage_service", lambda: fake)
    monkeypatch.setattr(retention, "load_storage_retention_state", lambda: {})
    monkeypatch.setattr(retention, "_save_state", lambda state: state)
    result = retention.run_storage_retention()
    assert result["state"] == "PARTIAL"
    assert result["apply_requested"] is True
    assert result["apply_enabled"] is True
    assert result["deleted_this_batch"] == 7
    assert len(fake.deleted) == 7
    oversize = {row["name"]: row for row in result["oversize_documents"]}
    assert oversize["repositories/strategy_decisions.json"]["protected"] is True
    assert oversize["repositories/market_snapshots.json"]["protected"] is False


def test_retention_blocks_apply_when_postgres_not_ready(monkeypatch):
    class FakeStorage:
        def health(self):
            return SimpleNamespace(to_dict=lambda: {"ok": False, "backend": "postgres", "message": "recovery mode"})

    monkeypatch.setenv("DATABASE_URL", "postgres://example")
    monkeypatch.setenv("STORAGE_RETENTION_APPLY", "True")
    monkeypatch.setattr(retention, "get_storage_service", lambda: FakeStorage())
    monkeypatch.setattr(retention, "load_storage_retention_state", lambda: {"pending_after_batch": 12})
    monkeypatch.setattr(retention, "_save_state", lambda state: state)
    result = retention.run_storage_retention()
    assert result["state"] == "BLOCKED_DATABASE"
    assert result["apply_requested"] is True
    assert result["apply_enabled"] is False
    assert "PostgreSQL" in result["disable_reason"]
    assert result["pending_after_batch"] == 12


def test_scanner_storage_finalization_is_not_misreported_as_analysis_failure(monkeypatch):
    import paper_scanner_runtime

    monkeypatch.setattr(paper_scanner_runtime, "load_scanner_status", lambda: {
        "scan_run_id": "SCAN-1",
        "tickers_processed": 30,
        "tickers_total": 30,
        "phase": "FINALIZING",
    })
    exc = RuntimeError("connection failed: the database system is in recovery mode")
    result = runner._scanner_failure_state(exc)
    assert result["state"] == "FINALIZATION_PENDING_STORAGE"
    assert result["analysis_completed"] is True
    assert result["tickers_processed"] == 30
    assert result["tickers_total"] == 30


def test_overall_state_is_truthful_for_maintenance_failure():
    state = {
        "state": "COMPLETED",
        "paper_scanner": {"state": "COMPLETED"},
        "learning_observation_maintenance": {"status": "FAILED"},
        "report_repair": {"state": "COMPLETED"},
        "report_revalidation": {"state": "NOT_DUE"},
        "storage_retention": {"state": "PARTIAL"},
        "report_delivery_retry": {"state": "COMPLETED"},
        "required_reports": {"state": "COMPLETED"},
    }
    assert runner._derive_overall_state(state) == "COMPLETED_WITH_WARNINGS"
    assert "learning_observation_maintenance:FAILED" in state["degraded_components"]


def test_production_closure_requires_effective_retention_and_no_degradation():
    state = {
        "database_preflight": {"ready": True},
        "runtime_alignment": {"aligned": True},
        "cluster_alignment": {"aligned": True},
        "storage_retention": {"apply_requested": True, "apply_enabled": True, "state": "PARTIAL"},
        "paper_scanner": {"state": "COMPLETED"},
        "degraded_components": [],
    }
    receipt = runner._production_closure_snapshot(state)
    assert receipt["state"] == "CRON_ACCEPTED"
    assert receipt["blockers"] == []


def test_paper_portfolio_never_falls_back_to_local_json_when_postgres_fails(monkeypatch):
    import paper_store
    from services.storage_service import StorageUnavailableError

    monkeypatch.setattr(paper_store, "using_postgres", lambda: True)
    monkeypatch.setattr(paper_store, "init_db", lambda: (_ for _ in ()).throw(RuntimeError("database recovery mode")))
    monkeypatch.setattr(paper_store, "_load_json", lambda: (_ for _ in ()).throw(AssertionError("local fallback forbidden")))
    try:
        paper_store.load_portfolio()
        raise AssertionError("expected StorageUnavailableError")
    except StorageUnavailableError:
        pass


def test_paper_portfolio_save_never_writes_local_fallback_in_production(monkeypatch):
    import paper_store
    from services.storage_service import StorageUnavailableError

    monkeypatch.setattr(paper_store, "using_postgres", lambda: True)
    monkeypatch.setattr(paper_store, "init_db", lambda: (_ for _ in ()).throw(RuntimeError("database recovery mode")))
    monkeypatch.setattr(paper_store, "_save_json", lambda value: (_ for _ in ()).throw(AssertionError("local fallback forbidden")))
    try:
        paper_store.save_portfolio({"cash": 1, "positions": {}, "trades": []})
        raise AssertionError("expected StorageUnavailableError")
    except StorageUnavailableError:
        pass
