from __future__ import annotations

from app_version import APP_VERSION
from repositories.application import RepositoryRegistry
from services.autonomy_learning_account_service import AutonomyLearningAccountService
from services.simulated_execution_service import SimulatedExecutionService
from services.storage_service import StorageService
from services.strategy_account_service import StrategyAccountService
from services.strategy_registry_service import StrategyRegistryService


def _services(tmp_path):
    storage = StorageService(base_dir=tmp_path, mode="local", allow_local_fallback=True)
    repositories = RepositoryRegistry(storage)
    registry = StrategyRegistryService(repositories)
    accounts = StrategyAccountService(repositories, registry)
    execution = SimulatedExecutionService(repositories, accounts)
    return accounts, AutonomyLearningAccountService(accounts, execution)


def _candidate(ticker: str, **changes):
    row = {
        "ticker": ticker, "investment_score": 63.0, "data_quality_score": 80.0,
        "risk_score": 75.0, "price": 100.0, "valid_for_decision": True,
        "evidence_valid_for_decision": False, "portfolio_action": "REVIEW",
        "autonomy_outcome_code": "OVERVÅKET",
    }
    row.update(changes)
    return row


def test_rc1626_identity_and_learning_profile(tmp_path):
    accounts, learning = _services(tmp_path)
    policy = learning.ensure_approved_profile()
    assert APP_VERSION == "v19.22.0-rc16.28"
    assert policy["minimum_score"] == 63.0
    assert policy["maximum_risk_score"] == 75.0
    assert policy["notional_value"] == 15000.0
    assert policy["maximum_buys_per_cycle"] == 3
    assert accounts.get("autonomy_main")["status"] == "PAUSED"


def test_learning_accepts_missing_noncritical_evidence_and_records_production_blockers(tmp_path):
    accounts, learning = _services(tmp_path)
    result = learning.run_cycle([_candidate("LEARN.OL")], run_id="RC1626-A", production_parameters={
        "minimum_investment_score": 78.0, "minimum_data_quality": 55.0, "maximum_risk_score": 65.0,
    })
    assert result["buy_count"] == 1
    position = accounts.get("autonomy_learning")["positions"]["LEARN.OL"]
    assert round(position["quantity"] * position["average_price"], 2) == 15000.0
    assert position["metadata"]["evidence_valid_at_entry"] is False
    assert "Score under produksjonsgrensen" in position["metadata"]["production_blockers_at_entry"]
    assert "Risiko over produksjonsgrensen" in position["metadata"]["production_blockers_at_entry"]


def test_learning_keeps_market_data_and_integrity_fail_closed(tmp_path):
    accounts, learning = _services(tmp_path)
    result = learning.run_cycle([
        _candidate("BADMARKET.OL", valid_for_decision=False),
        _candidate("BADINTEGRITY.OL", critical_integrity_error=True),
        _candidate("TOORISKY.OL", risk_score=75.1),
    ], run_id="RC1626-B")
    assert result["buy_count"] == 0
    assert accounts.get("autonomy_learning")["positions"] == {}
    reasons = " | ".join(str(row.get("reason")) for row in result["decisions"])
    assert "ikke beslutningsgyldige" in reasons
    assert "Kritisk integritetsfeil" in reasons
    assert "over hard grense 75.0" in reasons


def test_fresh_paper_buy_can_open_learning_entry_despite_generic_wait(tmp_path):
    accounts, learning = _services(tmp_path)
    paper = {"technical_decisions": [{"action": "BUY", "confidence": 81.0}], "source_run_id": "PAPER-1"}
    result = learning.run_cycle([_candidate("PAPER.OL", technical_entry_wait=True, paper_engine_input=paper)], run_id="RC1626-C")
    assert result["buy_count"] == 1
    metadata = accounts.get("autonomy_learning")["positions"]["PAPER.OL"]["metadata"]
    assert metadata["paper_signal"]["action"] == "BUY"
    assert metadata["paper_signal"]["execution_authorized"] is False


def test_learning_records_horizon_measurement_and_executes_paper_sell(tmp_path):
    accounts, learning = _services(tmp_path)
    learning.run_cycle([_candidate("EXIT.OL", market_date="2026-08-07")], run_id="RC1626-D1")
    sell_signal = {"technical_decisions": [{"action": "SELL", "confidence": 80.0}], "source_run_id": "PAPER-SELL"}
    result = learning.run_cycle([
        _candidate("EXIT.OL", price=102.0, market_date="2026-08-08", paper_engine_input=sell_signal)
    ], run_id="RC1626-D2")
    assert result["sell_count"] == 1
    assert "EXIT.OL" not in accounts.get("autonomy_learning")["positions"]
    sell_fill = next(row for row in result["fills"] if row["side"] == "SELL")
    measurements = sell_fill["metadata"]["outcome_measurements"]
    assert measurements[0]["horizon_days"] == 1
    assert measurements[0]["return_pct"] == 2.0
