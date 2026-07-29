from __future__ import annotations

from pathlib import Path

from app_version import APP_VERSION, get_version_contract
from domain.strategy_contract import validate_strategy_decision
from repositories.application import RepositoryRegistry
from services.market_snapshot_service import MarketSnapshotService
from services.parallel_strategy_service import ParallelStrategyService
from services.storage_service import StorageService
from services.strategy_registry_service import StrategyRegistryService
from services.technical_signal_service import TechnicalSignalService


def _services(tmp_path):
    storage = StorageService(base_dir=tmp_path, database_url="", mode="local")
    repositories = RepositoryRegistry(storage)
    registry = StrategyRegistryService(repositories)
    registry.ensure_defaults()
    snapshots = MarketSnapshotService(repositories)
    technical = TechnicalSignalService(snapshots)
    parallel = ParallelStrategyService(repositories, registry, technical)
    return repositories, registry, snapshots, parallel


def _snapshot(snapshots):
    return snapshots.build_market_snapshot(
        [{
            "ticker": "EQNR.OL",
            "score": 6.0,
            "scanner_score": 60.0,
            "investment_score": 82.0,
            "risk_score": 30.0,
            "data_quality": 90.0,
            "price": 300.0,
            "technical": {
                "rsi": 55,
                "trend": "up",
                "macd_bullish": True,
                "breakout_type": "bullish",
                "channel_pos": 50,
            },
        }],
        run_id="RUN-1970",
        source="test_v1970",
        captured_at="2026-07-26T10:00:00+00:00",
    )


def test_version_contract_exposes_shared_strategy_interface():
    assert APP_VERSION == "v19.14.4"
    contract = get_version_contract()
    assert contract["strategy_interface_version"] == "1.0"
    assert contract["parallel_strategy_service_version"] == "1.1"
    assert contract["technical_signal_service_version"] == "1.1"


def test_parallel_versions_use_same_snapshot_and_never_authorize_execution(tmp_path):
    _, registry, snapshots, parallel = _services(tmp_path)
    production = registry.production_for_family("technical")
    challenger = registry.create_challenger(
        production["version_id"],
        "2.0.0",
        parameter_version="technical-strict-2",
        metadata={"technical_parameters": {"buy_score_threshold": 8.5}},
    )
    registry.set_status(challenger["version_id"], "CHALLENGER")
    snapshot = _snapshot(snapshots)
    result = parallel.evaluate_snapshot(
        snapshot,
        families=["technical"],
        portfolio_states={"technical": {"positions": {}}},
    )
    assert result["strategy_count"] == 3
    assert result["decision_count"] == 3
    assert result["error_count"] == 0
    decisions = result["decisions"]
    assert {row["market_snapshot_id"] for row in decisions} == {snapshot.snapshot_id}
    assert {row["candidate_snapshot_id"] for row in decisions} == {snapshot.candidates[0]["candidate_snapshot_id"]}
    assert all(row["execution_authorized"] is False for row in decisions)
    by_version = {row["strategy_version"]: row for row in decisions}
    assert by_version["legacy-1.0.0"]["action"] == "BUY"
    assert by_version["2.0.0"]["action"] == "HOLD"


def test_common_decision_contract_is_valid(tmp_path):
    _, _, snapshots, parallel = _services(tmp_path)
    result = parallel.evaluate_snapshot(_snapshot(snapshots), families=["technical"])
    decision = result["decisions"][0]
    assert validate_strategy_decision(decision)["ok"] is True
    assert decision["order_intent"]["status"] == "PROPOSED_ONLY"


def test_autonomy_and_technical_evaluate_same_snapshot(tmp_path):
    _, _, snapshots, parallel = _services(tmp_path)
    snapshot = _snapshot(snapshots)
    from autonomous_portfolio import AutonomousParameters
    result = parallel.evaluate_snapshot(
        snapshot,
        families=["technical", "autonomy"],
        portfolio_states={
            "technical": {"positions": {}},
            "autonomy": {"status": "ACTIVE", "positions": {}, "cash": 100000.0},
        },
        context_metadata={"autonomy_parameters": AutonomousParameters().normalized()},
    )
    families = {row["strategy_family"] for row in result["decisions"]}
    assert families == {"technical", "autonomy"}
    assert {row["market_snapshot_id"] for row in result["decisions"]} == {snapshot.snapshot_id}
    autonomy = next(row for row in result["decisions"] if row["strategy_family"] == "autonomy")
    assert autonomy["action"] == "BUY"
    assert autonomy["score"] == 82.0


def test_parallel_results_persist_and_rehydrate(tmp_path):
    _, _, snapshots, parallel = _services(tmp_path)
    result = parallel.evaluate_snapshot(_snapshot(snapshots), families=["technical", "autonomy"])
    repositories2 = RepositoryRegistry(StorageService(base_dir=tmp_path, database_url="", mode="local"))
    registry2 = StrategyRegistryService(repositories2)
    snapshots2 = MarketSnapshotService(repositories2)
    parallel2 = ParallelStrategyService(repositories2, registry2, TechnicalSignalService(snapshots2))
    loaded_run = repositories2.strategy_runs.get(result["strategy_run_id"])
    assert loaded_run is not None
    assert loaded_run["decision_count"] == result["decision_count"]
    assert len(parallel2.recent_decisions()) == result["decision_count"]


def test_strategy_failure_is_isolated(tmp_path, monkeypatch):
    _, registry, snapshots, parallel = _services(tmp_path)
    production = registry.production_for_family("technical")
    challenger = registry.create_challenger(production["version_id"], "broken-1", parameter_version="broken")
    registry.set_status(challenger["version_id"], "CHALLENGER")
    original = parallel._implementation

    class Broken:
        def evaluate(self, candidate, context):
            raise RuntimeError("synthetic challenger failure")

    def implementation(version):
        if version.get("strategy_version") == "broken-1":
            return Broken()
        return original(version)

    monkeypatch.setattr(parallel, "_implementation", implementation)
    result = parallel.evaluate_snapshot(_snapshot(snapshots), families=["technical"])
    assert result["decision_count"] == 3
    assert result["error_count"] == 1
    assert any(row["action"] == "BUY" for row in result["decisions"])
    failed = next(row for row in result["decisions"] if row["action"] == "ERROR")
    assert "synthetic challenger failure" in failed["error"]
    assert failed["execution_authorized"] is False


def test_paused_and_retired_versions_do_not_run(tmp_path):
    _, registry, snapshots, parallel = _services(tmp_path)
    production = registry.production_for_family("technical")
    challenger = registry.create_challenger(production["version_id"], "paused-1")
    registry.set_status(challenger["version_id"], "PAUSED")
    result = parallel.evaluate_snapshot(_snapshot(snapshots), families=["technical"])
    assert result["strategy_count"] == 2
    assert {row["strategy_version"] for row in result["decisions"]} == {"legacy-1.0.0", "1.1.0"}


def test_parallel_service_has_no_order_execution_dependency():
    source = Path("services/parallel_strategy_service.py").read_text(encoding="utf-8")
    assert "paper_buy" not in source
    assert "paper_sell" not in source
    assert "auto_trade" not in source
    assert "run_autonomous_cycle" not in source
    assert 'execution_authorized=False' in source


def test_scanner_and_autonomy_use_fail_open_parallel_runner():
    scanner = Path("scanner_worker.py").read_text(encoding="utf-8")
    autonomy = Path("autonomous_portfolio.py").read_text(encoding="utf-8")
    assert "paper_scanner_parallel" in scanner
    assert "Parallel strategikjøring feilet isolert" in scanner
    assert "autonomy_cycle_parallel" in autonomy
    assert "PARALLEL_STRATEGY_CYCLE_FAILED" in autonomy
    assert 'families=["technical", "autonomy"]' in autonomy


def test_service_registry_exposes_parallel_runner():
    source = Path("services/service_registry.py").read_text(encoding="utf-8")
    assert "self.parallel_strategies = ParallelStrategyService" in source


def test_startup_hotfix_is_included():
    source = Path("ui/global_styles.py").read_text(encoding="utf-8")
    assert "import logging" in source
    assert "from ui_trust import ui_consistency_tokens" in source


def test_strategy_page_exposes_parallel_runs_and_bounded_challenger_parameters():
    source = Path("pages/strategy_versions.py").read_text(encoding="utf-8")
    assert "Parallelle strategikjøringer" in source
    assert "technical_parameters" in source
    assert "execution_authorized=false" in source


def test_style_injection_executes_with_runtime_dependencies(monkeypatch):
    import importlib.util
    import sys
    import types

    calls = []
    fake_streamlit = types.ModuleType("streamlit")
    fake_streamlit.markdown = lambda *args, **kwargs: calls.append((args, kwargs))
    monkeypatch.setitem(sys.modules, "streamlit", fake_streamlit)
    spec = importlib.util.spec_from_file_location("global_styles_v1970_startup_test", "ui/global_styles.py")
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    module.inject_foundation_styles_v1950()
    module.inject_final_density_styles_v1950()
    assert len(calls) == 7
