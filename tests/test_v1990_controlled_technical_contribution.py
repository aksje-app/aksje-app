from __future__ import annotations

import io
import json
from pathlib import Path
import zipfile

import pytest

from app_version import APP_VERSION, get_version_contract
from repositories.application import RepositoryRegistry
from services.storage_service import StorageService
from services.autonomy_technical_contribution_service import AutonomyTechnicalContributionService
from services.autonomy_activation_service import AutonomyActivationService, classify_blocker
from services.strategy_registry_service import StrategyRegistryService
from services.strategy_account_service import StrategyAccountService
from services.simulated_execution_service import SimulatedExecutionService
from services.evaluation_export_service import EvaluationExportService

ROOT = Path(__file__).resolve().parents[1]


def build_services(tmp_path):
    storage = StorageService(base_dir=tmp_path, mode="local", allow_local_fallback=True)
    repos = RepositoryRegistry(storage)
    registry = StrategyRegistryService(repos)
    accounts = StrategyAccountService(repos, registry)
    execution = SimulatedExecutionService(repos, accounts)
    activation = AutonomyActivationService(repos)
    technical = AutonomyTechnicalContributionService(repos)
    export = EvaluationExportService(repos, activation, accounts, execution)
    return repos, technical, activation, export


def technical_decision(ticker: str, *, score: float, confidence: float = 80, action: str = "BUY", status: str = "PRODUCTION", version: str = "technical_benchmark@legacy-1.0.0"):
    return {
        "ticker": ticker,
        "strategy_family": "technical",
        "strategy_status": status,
        "strategy_version_id": version,
        "strategy_version": version.split("@")[-1],
        "action": action,
        "raw_decision": action,
        "score": score,
        "confidence": confidence,
        "candidate_snapshot_id": f"CS-{ticker}",
        "market_snapshot_id": "MS-1",
        "metadata": {"technical_result": {"technical_model_version": "legacy-1.0.0", "technical_parameter_version": "paper-current"}},
    }


def test_version_contract_v1990():
    contract = get_version_contract()
    assert APP_VERSION.startswith("v19.22.0-rc")
    assert contract["autonomy_technical_contribution_service_version"] == "1.0"
    assert contract["evaluation_export_service_version"] == "1.5"


def test_default_policy_is_bounded_paper_entry_only(tmp_path):
    _repos, service, _activation, _export = build_services(tmp_path)
    policy = service.policy()
    assert policy["enabled"] is True
    assert policy["scope"] == "ENTRY_ONLY"
    assert policy["execution_scope"] == "PAPER_ONLY"
    assert 0 <= policy["weight_pct"] <= 20
    assert policy["production_technical_only"] is True
    assert policy["bound_technical_strategy_version_id"] == "technical_benchmark@legacy-1.0.0"
    assert policy["hard_gates_unchanged"] is True
    assert policy["automatic_policy_changes"] is False


def test_only_production_technical_version_contributes(tmp_path):
    _repos, service, _activation, _export = build_services(tmp_path)
    result = service.apply(
        [{"ticker": "EQNR.OL", "investment_score": 76}],
        parallel_strategy_run={"decisions": [
            technical_decision("EQNR.OL", score=10, status="CHALLENGER", version="technical_benchmark@challenger"),
            technical_decision("EQNR.OL", score=8, status="PRODUCTION"),
        ]},
        run_id="R1", minimum_investment_score=78,
    )
    row = result["candidates"][0]
    assert row["technical_strategy_version_id"] == "technical_benchmark@legacy-1.0.0"
    assert row["technical_score_100"] == 80
    assert row["autonomy_adjusted_investment_score"] == 80
    assert row["technical_contribution_points"] == 4
    assert row["technical_can_authorize_execution"] is False



def test_unbound_new_production_version_cannot_change_autonomy_automatically(tmp_path):
    _repos, service, _activation, _export = build_services(tmp_path)
    result = service.apply(
        [{"ticker": "NEW.OL", "investment_score": 76}],
        parallel_strategy_run={"decisions": [technical_decision("NEW.OL", score=10, status="PRODUCTION", version="technical_benchmark@new-2.0.0")]},
        run_id="BOUND-1", minimum_investment_score=78,
    )
    row = result["candidates"][0]
    assert row["technical_contribution_applied"] is False
    assert row["autonomy_adjusted_investment_score"] == 76
    assert result["summary"]["bound_technical_strategy_version_id"] == "technical_benchmark@legacy-1.0.0"

def test_positive_contribution_cannot_lift_candidate_below_base_floor(tmp_path):
    _repos, service, _activation, _export = build_services(tmp_path)
    result = service.apply(
        [{"ticker": "WEAK.OL", "investment_score": 73}],
        parallel_strategy_run={"decisions": [technical_decision("WEAK.OL", score=10)]},
        run_id="R2", minimum_investment_score=78,
    )
    row = result["candidates"][0]
    assert row["autonomy_adjusted_investment_score"] == 73
    assert row["technical_contribution_points"] == 0
    assert row["technical_positive_gate"] == "BASE_SCORE_FLOOR"


def test_negative_signal_is_bounded_and_creates_wait(tmp_path):
    _repos, service, _activation, _export = build_services(tmp_path)
    result = service.apply(
        [{"ticker": "WAIT.OL", "investment_score": 84}],
        parallel_strategy_run={"decisions": [technical_decision("WAIT.OL", score=2, action="AVOID", confidence=75)]},
        run_id="R3", minimum_investment_score=78,
    )
    row = result["candidates"][0]
    assert row["technical_contribution_points"] == -4.5
    assert row["autonomy_adjusted_investment_score"] == 79.5
    assert row["technical_entry_wait"] is True
    assert row["technical_timing"] == "WAIT"
    assert result["summary"]["wait_count"] == 1



def test_explicit_avoid_creates_wait_even_when_bearish_score_confidence_is_low(tmp_path):
    _repos, service, _activation, _export = build_services(tmp_path)
    result = service.apply(
        [{"ticker": "BEAR.OL", "investment_score": 84}],
        parallel_strategy_run={"decisions": [technical_decision("BEAR.OL", score=0, action="AVOID", confidence=35)]},
        run_id="R3B", minimum_investment_score=78,
    )
    assert result["candidates"][0]["technical_entry_wait"] is True
    assert result["candidates"][0]["technical_timing"] == "WAIT"

def test_missing_technical_decision_fails_open_without_score_change(tmp_path):
    _repos, service, _activation, _export = build_services(tmp_path)
    result = service.apply(
        [{"ticker": "NO.OL", "investment_score": 79}],
        parallel_strategy_run={"decisions": []}, run_id="R4", minimum_investment_score=78,
    )
    row = result["candidates"][0]
    assert row["autonomy_adjusted_investment_score"] == 79
    assert row["technical_contribution_applied"] is False
    assert row["technical_entry_wait"] is False


def test_policy_changes_require_approval_and_are_safely_bounded(tmp_path):
    _repos, service, _activation, _export = build_services(tmp_path)
    with pytest.raises(ValueError):
        service.update_policy({"weight_pct": 99}, approved_by="", reason="test")
    with pytest.raises(ValueError):
        service.update_policy({"weight_pct": 99}, approved_by="qa", reason="")
    changed = service.update_policy({
        "weight_pct": 99, "maximum_positive_points": 99, "maximum_negative_points": 99,
        "minimum_base_score_floor": 1, "wait_below_technical_score": 99,
    }, approved_by="qa", reason="boundary")
    policy = changed["policy"]
    assert policy["weight_pct"] == 20
    assert policy["maximum_positive_points"] == 5
    assert policy["maximum_negative_points"] == 8
    assert policy["minimum_base_score_floor"] == 70
    assert policy["wait_below_technical_score"] == 45
    assert policy["hard_gates_unchanged"] is True
    assert changed["rollback"]["weight_pct"] == 15


def test_activation_classifies_technical_wait():
    code, _label = classify_blocker({"action": "WAIT", "reason": "Teknisk produksjonsbenchmark legacy: AVOID, teknisk timing gir VENT"})
    assert code == "TECHNICAL_TIMING_WAIT"


def test_export_contains_technical_contribution_csv_and_policy(tmp_path):
    repos, service, activation, export = build_services(tmp_path)
    service.policy()
    analysis = activation.analyse([{
        "run_id": "ZIP-99", "ticker": "EQNR.OL", "action": "WAIT", "reason": "Teknisk timing gir VENT",
        "score": 79.5, "base_score": 84, "data_quality_score": 90, "risk_score": 20,
        "technical_contribution_applied": True, "technical_contribution_points": -4.5,
        "technical_score_100": 20, "technical_signal_confidence": 75,
        "technical_signal_action": "AVOID", "technical_timing": "WAIT", "technical_entry_wait": True,
        "technical_strategy_version_id": "technical_benchmark@legacy-1.0.0",
    }], run_id="ZIP-99", parameters={"minimum_investment_score": 78, "minimum_data_quality": 55, "maximum_risk_score": 65})
    payload = export.build_zip(analysis=analysis)
    with zipfile.ZipFile(io.BytesIO(payload)) as archive:
        assert "technical_contribution.csv" in archive.namelist()
        text = archive.read("technical_contribution.csv").decode("utf-8-sig")
        assert "technical_benchmark@legacy-1.0.0" in text
        parameters = json.loads(archive.read("parameter_snapshot.json"))
        assert parameters["autonomy_technical_contribution_policy"]["scope"] == "ENTRY_ONLY"
        manifest = json.loads(archive.read("manifest.json"))
        assert manifest["app_version"] == APP_VERSION
        assert len(manifest["files"]) == 20  # manifest itself is added after checksums; ZIP has 21 files


def test_source_integration_contracts_v1990():
    autonomous = (ROOT / "autonomous_portfolio.py").read_text(encoding="utf-8")
    learning = (ROOT / "services" / "autonomy_learning_account_service.py").read_text(encoding="utf-8")
    export = (ROOT / "services" / "evaluation_export_service.py").read_text(encoding="utf-8")
    assert "get_autonomy_technical_contribution_service().apply" in autonomous
    assert "TECHNICAL_TIMING_WAIT" in autonomous
    assert "_candidate_entry_score" in autonomous
    assert "autonomy_adjusted_investment_score" in learning
    assert "technical_contribution.csv" in export
    assert "Skriv GODKJENN for å lagre teknisk bidragsprofil" in autonomous
