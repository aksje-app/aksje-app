from __future__ import annotations

import scheduled_runner as runner
import storage_retention as retention


def test_retention_release_default_applies_when_render_omits_single_env(monkeypatch):
    monkeypatch.delenv("STORAGE_RETENTION_APPLY", raising=False)
    monkeypatch.delenv("STORAGE_RETENTION_ENABLED", raising=False)
    monkeypatch.delenv("STORAGE_RETENTION_DELETE_ENABLED", raising=False)
    monkeypatch.delenv("STORAGE_RETENTION_MODE", raising=False)
    monkeypatch.setenv("STORAGE_RETENTION_BATCH_SIZE", "20")
    monkeypatch.setenv("STORAGE_RETENTION_TIME_BUDGET_SECONDS", "45")
    config = retention.retention_configuration()
    assert config["raw_apply_env"] is None
    assert config["apply_env_missing"] is True
    assert config["apply_config_source"] == "RELEASE_DEFAULT_APPLY_WHEN_ENV_MISSING"
    assert config["parsed_apply_enabled"] is True


def test_explicit_retention_false_overrides_release_default(monkeypatch):
    monkeypatch.setenv("STORAGE_RETENTION_APPLY", "False")
    config = retention.retention_configuration()
    assert config["apply_env_missing"] is False
    assert config["parsed_apply_enabled"] is False


def test_wrapped_storage_recovery_is_classified_from_exception_cause(monkeypatch):
    import paper_scanner_runtime
    from services.storage_service import StorageUnavailableError

    monkeypatch.setattr(paper_scanner_runtime, "load_scanner_status", lambda: {
        "scan_run_id": "SCAN-WRAPPED",
        "tickers_processed": 30,
        "tickers_total": 30,
        "phase": "FINALIZING",
    })
    try:
        try:
            raise RuntimeError("FATAL: the database system is in recovery mode")
        except RuntimeError as inner:
            raise StorageUnavailableError("paper_portfolio PostgreSQL load feilet") from inner
    except StorageUnavailableError as exc:
        result = runner._scanner_failure_state(exc)
    assert result["state"] == "FINALIZATION_PENDING_STORAGE"
    assert result["analysis_completed"] is True


def test_mid_scan_wrapped_recovery_is_deferred_not_failed(monkeypatch):
    import paper_scanner_runtime
    from services.storage_service import StorageUnavailableError

    monkeypatch.setattr(paper_scanner_runtime, "load_scanner_status", lambda: {
        "scan_run_id": "SCAN-MID",
        "tickers_processed": 12,
        "tickers_total": 30,
        "phase": "SCANNING",
    })
    exc = StorageUnavailableError("write_json(scanner checkpoint) feilet")
    result = runner._scanner_failure_state(exc)
    assert result["state"] == "DEFERRED_DATABASE"
    assert runner._derive_overall_state({"state":"RUNNING", "paper_scanner": result}) == "DEFERRED_DATABASE"
