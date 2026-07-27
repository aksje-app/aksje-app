from __future__ import annotations

import json
from pathlib import Path

import pytest

from repositories.application import RepositoryRegistry
from services.storage_service import StorageService
from services.strategy_registry_service import StrategyRegistryService
from services.strategy_account_service import StrategyAccountService
from services.simulated_execution_service import SimulatedExecutionService
from services.paper_migration_service import PaperMigrationService


def service(tmp_path: Path) -> PaperMigrationService:
    storage = StorageService(base_dir=tmp_path / "storage", mode="local", allow_local_fallback=True)
    repos = RepositoryRegistry(storage)
    accounts = StrategyAccountService(repos, StrategyRegistryService(repos))
    execution = SimulatedExecutionService(repos, accounts)
    accounts.ensure_defaults()
    return PaperMigrationService(accounts, execution)


def legacy_payload():
    return {
        "cash": 87500.0,
        "initial_cash": 100000.0,
        "realized_pnl": 2500.0,
        "positions": {
            "EQNR.OL": {"shares": 100, "entry_price": 100.0, "last_price": 110.0},
            "DNB.OL": {"quantity": 50, "average_price": 200.0, "last_price": 205.0},
        },
        "trades": [
            {"trade_id": "T1", "time": "2026-07-20T10:00:00Z", "type": "BUY", "ticker": "EQNR.OL", "price": 100.0, "shares": 100, "amount": 10000.0},
            {"trade_id": "T2", "time": "2026-07-21T10:00:00Z", "type": "BUY", "ticker": "DNB.OL", "price": 200.0, "shares": 50, "amount": 10000.0},
        ],
    }


def test_dry_run_does_not_change_account_or_ledger(tmp_path):
    svc = service(tmp_path)
    before = json.loads(json.dumps(svc.accounts.get("technical_benchmark_main")))
    result = svc.inspect(legacy_payload(), source="test")
    assert result["runtime_cutover"] is False
    assert result["legacy_delete"] is False
    assert svc.accounts.get("technical_benchmark_main") == before
    assert svc.repositories.strategy_orders.list() == []


def test_migration_requires_explicit_confirmation_and_reason(tmp_path):
    svc = service(tmp_path)
    with pytest.raises(ValueError, match="MIGRER"):
        svc.migrate(legacy_payload(), source="test", output_dir=tmp_path / "out", confirmation="JA", reason="test")
    with pytest.raises(ValueError, match="Begrunnelse"):
        svc.migrate(legacy_payload(), source="test", output_dir=tmp_path / "out", confirmation="MIGRER", reason="")


def test_migration_backups_reconciles_and_preserves_binding(tmp_path):
    svc = service(tmp_path)
    bindings_before = json.loads(json.dumps(svc.repositories.strategy_production_bindings.list()))
    result = svc.migrate(legacy_payload(), source="test", output_dir=tmp_path / "out", confirmation="MIGRER", reason="QA")
    assert result["ok"] is True
    assert result["reconciliation"]["ok"] is True
    assert result["mirrored_trades"] == 2
    assert result["production_binding_unchanged"] is True
    assert result["runtime_cutover"] is False
    assert result["legacy_deleted"] is False
    assert svc.repositories.strategy_production_bindings.list() == bindings_before
    assert Path(result["backup_path"]).is_file()
    assert Path(result["report_path"]).is_file()
    account = svc.accounts.get("technical_benchmark_main")
    assert account["cash"] == 87500.0
    assert account["positions"]["EQNR.OL"]["quantity"] == 100.0


def test_second_run_is_idempotent_and_does_not_duplicate_ledger(tmp_path):
    svc = service(tmp_path)
    out = tmp_path / "out"
    first = svc.migrate(legacy_payload(), source="test", output_dir=out, confirmation="MIGRER", reason="first")
    second = svc.migrate(legacy_payload(), source="test", output_dir=out, confirmation="MIGRER", reason="second")
    assert first["mirrored_trades"] == 2
    assert second["mirrored_trades"] == 0
    assert second["already_present_trades"] == 2
    assert second["ledger_after"] == first["ledger_after"]
    assert len(list(out.glob("paper_legacy_backup_*.json"))) == 1
    assert second["ok"] is True


def test_tool_is_isolated_from_active_runtime():
    root = Path(__file__).resolve().parents[1]
    source = (root / "tools" / "migrate_paper_foundation_v19130.py").read_text(encoding="utf-8")
    assert "scanner_worker" not in source
    assert "trading_engine" not in source
    assert "paper_store" not in source
