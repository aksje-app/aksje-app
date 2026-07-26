from __future__ import annotations

import io
import json
from pathlib import Path
import zipfile

from app_version import APP_VERSION, get_version_contract
from repositories.application import RepositoryRegistry
from services.storage_service import StorageService
from services.strategy_registry_service import StrategyRegistryService
from services.strategy_account_service import StrategyAccountService
from services.simulated_execution_service import SimulatedExecutionService
from services.autonomy_activation_service import AutonomyActivationService, classify_blocker
from services.autonomy_learning_account_service import AutonomyLearningAccountService
from services.evaluation_export_service import EvaluationExportService


ROOT = Path(__file__).resolve().parents[1]


def services(tmp_path):
    storage = StorageService(base_dir=tmp_path, mode="local", allow_local_fallback=True)
    repositories = RepositoryRegistry(storage)
    registry = StrategyRegistryService(repositories)
    accounts = StrategyAccountService(repositories, registry)
    execution = SimulatedExecutionService(repositories, accounts)
    activation = AutonomyActivationService(repositories)
    learning = AutonomyLearningAccountService(accounts, execution)
    export = EvaluationExportService(repositories, activation, accounts, execution)
    return repositories, registry, accounts, execution, activation, learning, export


def test_v1980_version_contract():
    contract = get_version_contract()
    assert APP_VERSION == "v19.9.0"
    assert contract["strategy_account_service_version"] == "1.0"
    assert contract["simulated_execution_service_version"] == "1.0"
    assert contract["autonomy_activation_service_version"] == "1.0"
    assert contract["autonomy_learning_account_service_version"] == "1.0"
    assert contract["evaluation_export_service_version"] == "1.1"


def test_separate_default_accounts(tmp_path):
    _repos, _registry, accounts, _execution, _activation, _learning, _export = services(tmp_path)
    rows = {row["account_id"]: row for row in accounts.list_accounts()}
    assert set(rows) >= {"technical_benchmark_main", "autonomy_main", "autonomy_learning"}
    assert rows["technical_benchmark_main"]["cash"] == 100000.0
    assert rows["autonomy_main"]["cash"] == 500000.0
    assert rows["autonomy_learning"]["cash"] == 100000.0
    assert rows["autonomy_learning"]["metadata"]["maximum_position_pct"] <= 2.0
    assert rows["autonomy_learning"]["metadata"]["maximum_risk_score"] <= 65.0


def test_common_engine_isolates_accounts_and_executes_buy_sell(tmp_path):
    _repos, _registry, accounts, execution, _activation, _learning, _export = services(tmp_path)
    accounts.ensure_defaults()
    technical_before = accounts.get("technical_benchmark_main")["cash"]
    main_before = accounts.get("autonomy_main")["cash"]
    result = execution.execute_order(
        account_id="autonomy_learning", run_id="RUN-1", ticker="EQNR.OL", side="BUY",
        reference_price=100.0, quantity=10.0, reason="test", execution_authorized=True,
    )
    assert result["ok"] is True
    learning = accounts.get("autonomy_learning")
    assert learning["cash"] == 99000.0
    assert learning["positions"]["EQNR.OL"]["quantity"] == 10.0
    assert accounts.get("technical_benchmark_main")["cash"] == technical_before
    assert accounts.get("autonomy_main")["cash"] == main_before

    sold = execution.execute_order(
        account_id="autonomy_learning", run_id="RUN-2", ticker="EQNR.OL", side="SELL",
        reference_price=110.0, quantity=10.0, reason="exit", execution_authorized=True,
    )
    assert sold["ok"] is True
    assert accounts.get("autonomy_learning")["cash"] == 100100.0
    assert "EQNR.OL" not in accounts.get("autonomy_learning")["positions"]
    assert sold["fill"]["realized_pnl"] == 100.0


def test_read_only_or_paused_account_cannot_execute(tmp_path):
    _repos, _registry, accounts, execution, _activation, _learning, _export = services(tmp_path)
    accounts.ensure_defaults()
    blocked = execution.execute_order(
        account_id="autonomy_learning", run_id="R", ticker="DNB.OL", side="BUY",
        reference_price=200.0, quantity=1.0, execution_authorized=False,
    )
    assert blocked["ok"] is False
    assert blocked["order"]["rejection_code"] == "EXECUTION_NOT_AUTHORIZED"
    assert accounts.get("autonomy_learning")["cash"] == 100000.0

    main = accounts.get("autonomy_main")
    assert main["status"] == "PAUSED"
    paused = execution.execute_order(
        account_id="autonomy_main", run_id="R", ticker="DNB.OL", side="BUY",
        reference_price=200.0, quantity=1.0, execution_authorized=True,
    )
    assert paused["ok"] is False
    assert paused["order"]["rejection_code"] == "ACCOUNT_NOT_ACTIVE"


def test_legacy_mirror_does_not_apply_trade_twice(tmp_path):
    _repos, _registry, accounts, execution, _activation, _learning, _export = services(tmp_path)
    legacy = {"cash": 90000.0, "positions": {"EQNR.OL": {"shares": 100, "entry_price": 100, "last_price": 100}}, "trades": []}
    accounts.sync_legacy_account(
        "technical_benchmark_main", legacy, strategy_family="technical", strategy_id="technical_benchmark",
        strategy_version_id="technical_benchmark@legacy-1.0.0", display_name="Teknisk benchmark", role="BENCHMARK", status="ACTIVE", run_id="R1",
    )
    cash_before = accounts.get("technical_benchmark_main")["cash"]
    trade = {"trade_id": "T1", "time": "2026-07-26T10:00:00", "type": "BUY", "ticker": "EQNR.OL", "price": 100, "shares": 100, "amount": 10000}
    first = execution.mirror_legacy_trade(account_id="technical_benchmark_main", trade=trade, run_id="R1")
    second = execution.mirror_legacy_trade(account_id="technical_benchmark_main", trade=trade, run_id="R1")
    assert first["mirrored"] is True
    assert second["mirrored"] is False
    assert accounts.get("technical_benchmark_main")["cash"] == cash_before


def test_learning_account_uses_lower_score_but_keeps_hard_gates(tmp_path):
    _repos, _registry, accounts, execution, _activation, learning, _export = services(tmp_path)
    result = learning.run_cycle([
        {"ticker": "GOOD.OL", "investment_score": 73, "data_quality_score": 80, "risk_score": 40, "price": 100},
        {"ticker": "BADRISK.OL", "investment_score": 90, "data_quality_score": 90, "risk_score": 80, "price": 100},
        {"ticker": "BADDATA.OL", "investment_score": 90, "data_quality_score": 40, "risk_score": 20, "price": 100},
    ], run_id="LEARN-1")
    assert result["buy_count"] == 1
    assert "GOOD.OL" in accounts.get("autonomy_learning")["positions"]
    assert "BADRISK.OL" not in accounts.get("autonomy_learning")["positions"]
    assert "BADDATA.OL" not in accounts.get("autonomy_learning")["positions"]
    assert result["hard_risk_gates_unchanged"] is True


def test_learning_policy_change_is_explicit_bounded_and_does_not_touch_main(tmp_path):
    _repos, _registry, accounts, _execution, _activation, learning, _export = services(tmp_path)
    accounts.ensure_defaults()
    main_before = json.loads(json.dumps(accounts.get("autonomy_main")))
    changed = learning.update_policy({
        "minimum_score": 10, "maximum_position_pct": 50,
        "maximum_risk_score": 99, "minimum_data_quality": 1,
    }, approved_by="qa", reason="boundary test")
    policy = changed["policy"]
    assert policy["minimum_score"] == 65.0
    assert policy["maximum_position_pct"] == 2.0
    assert policy["maximum_risk_score"] == 65.0
    assert policy["minimum_data_quality"] == 55.0
    assert accounts.get("autonomy_main") == main_before
    history = accounts.get("autonomy_learning")["metadata"]["policy_history"]
    assert history[0]["approved_by"] == "qa"
    assert history[0]["rollback"]


def test_activation_funnel_and_threshold_simulation(tmp_path):
    _repos, _registry, accounts, _execution, activation, _learning, _export = services(tmp_path)
    analysis = activation.analyse([
        {"run_id": "A", "ticker": "A", "score": 77, "data_quality_score": 90, "risk_score": 20, "action": "SKIP", "reason": "Score 77.0 under terskel"},
        {"run_id": "A", "ticker": "B", "score": 80, "data_quality_score": 40, "risk_score": 20, "action": "SKIP", "reason": "Datakvalitet 40.0 under terskel"},
        {"run_id": "A", "ticker": "C", "score": 82, "data_quality_score": 90, "risk_score": 70, "action": "SKIP", "reason": "Risiko 70.0 over grense"},
        {"run_id": "A", "ticker": "D", "score": 85, "data_quality_score": 90, "risk_score": 20, "action": "BUY", "order_intent_created": True, "order_executed": True},
    ], run_id="A", parameters={"minimum_investment_score": 78, "minimum_data_quality": 55, "maximum_risk_score": 65}, account_metrics=accounts.comparison())
    assert analysis["funnel"]["candidates_received"] == 4
    assert analysis["funnel"]["passed_data_quality"] == 3
    assert analysis["funnel"]["passed_risk"] == 2
    assert analysis["funnel"]["passed_score"] == 1
    assert analysis["funnel"]["orders_executed"] == 1
    assert any(row["minimum_score"] == 72.0 and row["eligible_candidates"] == 2 for row in analysis["threshold_simulations"])
    assert classify_blocker({"action": "SKIP", "reason": "Utilstrekkelig kapital eller sektorrom"})[0] == "INSUFFICIENT_CAPITAL_OR_SECTOR"


def test_export_zip_contains_requested_safe_files_and_redacts_secrets(tmp_path):
    repos, _registry, accounts, execution, activation, _learning, export = services(tmp_path)
    analysis = activation.analyse([
        {"run_id": "ZIP", "ticker": "EQNR.OL", "score": 75, "data_quality_score": 90, "risk_score": 20, "action": "SKIP", "reason": "Score under terskel", "api_key": "do-not-share"},
    ], run_id="ZIP", parameters={"minimum_investment_score": 78, "minimum_data_quality": 55, "maximum_risk_score": 65}, account_metrics=accounts.comparison())
    payload = export.build_zip(analysis=analysis, errors=[{"error": "token=abc123 authorization=secret", "password": "pw"}], additional_metadata={"DATABASE_URL": "db-credential-placeholder"})
    with zipfile.ZipFile(io.BytesIO(payload)) as archive:
        names = set(archive.namelist())
        expected = {"test_summary.md", "activation_funnel.csv", "strategy_comparison.csv", "candidate_decisions.csv", "orders.csv", "trades.csv", "portfolio_metrics.csv", "parameter_snapshot.json", "run_metadata.json", "errors_sanitized.txt", "manifest.json"}
        assert expected <= names
        all_text = "\n".join(archive.read(name).decode("utf-8", errors="ignore") for name in names)
        assert "abc123" not in all_text
        assert "authorization=secret" not in all_text
        assert "do-not-share" not in all_text
        assert "db-credential-placeholder" not in all_text
        manifest = json.loads(archive.read("manifest.json"))
        assert manifest["contains_secrets"] is False
        assert manifest["app_version"] == "v19.9.0"


def test_source_integration_and_ui_contracts():
    autonomous = (ROOT / "autonomous_portfolio.py").read_text(encoding="utf-8")
    scanner = (ROOT / "scanner_worker.py").read_text(encoding="utf-8")
    repos = (ROOT / "repositories" / "application.py").read_text(encoding="utf-8")
    assert "get_autonomy_learning_account_service().run_cycle" in autonomous
    assert "get_autonomy_activation_service().analyse" in autonomous
    assert "Eksporter testresultater (ZIP)" in autonomous
    assert "Skriv GODKJENN" in autonomous
    assert "sync_legacy_account" in scanner
    assert "strategy_accounts" in repos and "strategy_orders" in repos and "strategy_fills" in repos
    assert "from ui_trust import ui_consistency_tokens" in (ROOT / "ui" / "global_styles.py").read_text(encoding="utf-8")
    export_tool = (ROOT / "tools" / "export_strategy_evaluation_v1980.py").read_text(encoding="utf-8")
    migrate_tool = (ROOT / "tools" / "migrate_strategy_accounts_v1980.py").read_text(encoding="utf-8")
    assert "from autonomous_portfolio" not in export_tool
    assert "from paper_store" not in migrate_tool and "from autonomous_portfolio" not in migrate_tool


def test_autonomy_quality_gate_reads_pipeline_data_quality_score():
    import autonomous_portfolio as ap
    assert ap._candidate_quality({"data_quality_score": 40, "confidence_score": 99}) == 40.0
    assert ap._candidate_quality({"data_quality": 42, "confidence_score": 99}) == 42.0
