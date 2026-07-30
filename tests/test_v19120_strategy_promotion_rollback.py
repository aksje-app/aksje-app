from __future__ import annotations

from app_version import APP_VERSION, get_version_contract
from domain.market_snapshot import CandidateSnapshot
from repositories.application import RepositoryRegistry
from services.production_strategy_service import ProductionStrategyService
from services.storage_service import StorageService
from services.strategy_promotion_service import StrategyPromotionError, StrategyPromotionService
from services.strategy_registry_service import StrategyRegistryService


def _stack(tmp_path):
    storage = StorageService(base_dir=tmp_path, database_url="", mode="local")
    repositories = RepositoryRegistry(storage)
    registry = StrategyRegistryService(repositories)
    registry.ensure_defaults()
    promotions = StrategyPromotionService(repositories, registry)
    return repositories, registry, promotions


def _seed_eligible_approval(repositories, *, outcome_pairs=24, delta=1.2, evidence_pct=92.0):
    experiment_id = "LAB-PROMOTION-ELIGIBLE"
    lab_run_id = "LABRUN-PROMOTION-ELIGIBLE"
    approval_id = "LABAPP-PROMOTION-ELIGIBLE"
    repositories.strategy_lab_experiments.upsert({
        "experiment_id": experiment_id,
        "name": "Promotion candidate",
        "baseline_version_id": "technical_benchmark@legacy-1.0.0",
        "challenger_version_ids": ["technical_quality_challenger@1.1.0"],
        "latest_lab_run_id": lab_run_id,
        "status": "APPROVED",
    })
    repositories.strategy_lab_runs.upsert({
        "lab_run_id": lab_run_id,
        "experiment_id": experiment_id,
        "error_count": 0,
        "metrics": [{
            "strategy_version_id": "technical_quality_challenger@1.1.0",
            "sufficient_evidence_pct": evidence_pct,
            "validation_outcome_samples": 12,
        }],
        "result_attribution": [{
            "challenger_version_id": "technical_quality_challenger@1.1.0",
            "baseline_version_id": "technical_benchmark@legacy-1.0.0",
            "outcome_pairs": outcome_pairs,
            "outcome_coverage_pct": 80.0,
            "attribution_reliable": outcome_pairs >= 20,
            "selection_return_delta_pct": delta,
            "avoided_losses": 8,
            "missed_gains": 4,
        }],
    })
    repositories.strategy_lab_approvals.upsert({
        "approval_id": approval_id,
        "experiment_id": experiment_id,
        "lab_run_id": lab_run_id,
        "status": "APPROVED_FOR_MANUAL_PROMOTION_REVIEW",
        "production_applied": False,
    })
    return approval_id


def _candidate(quality=20.0):
    return CandidateSnapshot.from_mapping({
        "candidate_snapshot_id": "CAND-PROMOTION",
        "market_snapshot_id": "MARKET-PROMOTION",
        "run_id": "RUN-PROMOTION",
        "ticker": "EQNR.OL",
        "price": 300.0,
        "base_score": 7.5,
        "data_quality": quality,
        "source_consensus": quality,
        "liquidity": quality,
        "decision_inputs": {
            "score": 7.5,
            "scanner_score": 75.0,
            "technical_score": 7.5,
            "data_quality": quality,
            "source_consensus": quality,
            "liquidity_score": quality,
            "technical": {"rsi": 55, "trend": "up", "macd_bullish": True, "breakout_type": "bullish", "channel_pos": 50},
        },
    })


def test_version_contract_exposes_promotion_and_router():
    assert APP_VERSION == "v19.15.0"
    contract = get_version_contract()
    assert contract["strategy_promotion_service_version"] == "1.0"
    assert contract["production_strategy_router_version"] == "1.0"


def test_canonical_bindings_bootstrap_and_persist(tmp_path):
    repositories, registry, _ = _stack(tmp_path)
    technical = repositories.strategy_production_bindings.get("technical")
    autonomy = repositories.strategy_production_bindings.get("autonomy")
    assert technical["version_id"] == "technical_benchmark@legacy-1.0.0"
    assert autonomy["version_id"] == "autonomy_main@1.0.0"
    recreated = StrategyRegistryService(RepositoryRegistry(StorageService(base_dir=tmp_path, database_url="", mode="local")))
    recreated.ensure_defaults()
    assert recreated.production_for_family("technical")["version_id"] == "technical_benchmark@legacy-1.0.0"


def test_preflight_blocks_preliminary_or_negative_evidence(tmp_path):
    repositories, _, promotions = _stack(tmp_path)
    approval_id = _seed_eligible_approval(repositories, outcome_pairs=8, delta=-0.5, evidence_pct=60.0)
    result = promotions.preflight(approval_id, "technical_quality_challenger@1.1.0")
    assert result["eligible"] is False
    assert any("For få observerte utfall" in item for item in result["blockers"])
    assert any("evidensdekning" in item.lower() for item in result["blockers"])
    assert any("ikke-negativ" in item for item in result["blockers"])


def test_explicit_promotion_changes_only_canonical_paper_binding(tmp_path):
    repositories, registry, promotions = _stack(tmp_path)
    approval_id = _seed_eligible_approval(repositories)
    check = promotions.preflight(approval_id, "technical_quality_challenger@1.1.0")
    assert check["eligible"] is True
    promoted = promotions.promote(
        approval_id,
        "technical_quality_challenger@1.1.0",
        actor="tester",
        reason="Reliable 5-day attribution and sufficient evidence",
        confirmation="PROMOTER",
    )
    assert promoted["status"] == "ACTIVE"
    assert promoted["automatic_promotion"] is False
    assert promoted["execution_authorized"] is False
    assert registry.production_for_family("technical")["version_id"] == "technical_quality_challenger@1.1.0"
    assert registry.get("technical_quality_challenger@1.1.0")["status"] == "PRODUCTION"
    assert registry.get("technical_benchmark@legacy-1.0.0")["status"] == "SHADOW"
    assert registry.production_for_family("autonomy")["version_id"] == "autonomy_main@1.0.0"
    assert repositories.strategy_lab_approvals.get(approval_id)["status"] == "PROMOTED"


def test_production_router_uses_promoted_quality_strategy_and_fails_closed(tmp_path):
    repositories, registry, promotions = _stack(tmp_path)
    approval_id = _seed_eligible_approval(repositories)
    promotions.promote(approval_id, "technical_quality_challenger@1.1.0", actor="tester", reason="test", confirmation="PROMOTER")
    router = ProductionStrategyService(registry)
    base = {"decision": "BUY", "score": 8.0, "decision_score": 8.0, "final_score": 8.0, "confidence": 90}
    result = router.evaluate_technical(_candidate(quality=20.0), base, run_id="ROUTER-TEST", portfolio_state={"positions": {}})
    assert result["production_strategy_version_id"] == "technical_quality_challenger@1.1.0"
    assert result["decision"] in {"AVOID", "HOLD / WAIT"}
    assert result["decision"] != "BUY"


def test_one_step_rollback_restores_exact_previous_binding(tmp_path):
    repositories, registry, promotions = _stack(tmp_path)
    approval_id = _seed_eligible_approval(repositories)
    promoted = promotions.promote(approval_id, "technical_quality_challenger@1.1.0", actor="tester", reason="test", confirmation="PROMOTER")
    rolled = promotions.rollback(promoted["promotion_id"], actor="tester", reason="Observed degradation", confirmation="RULL TILBAKE")
    assert rolled["status"] == "ROLLED_BACK"
    assert registry.production_for_family("technical")["version_id"] == "technical_benchmark@legacy-1.0.0"
    assert registry.get("technical_benchmark@legacy-1.0.0")["status"] == "PRODUCTION"
    assert registry.get("technical_quality_challenger@1.1.0")["status"] == "SHADOW"
    assert repositories.strategy_lab_approvals.get(approval_id)["status"] == "ROLLED_BACK_AFTER_PROMOTION"


def test_confirmation_and_reason_are_mandatory(tmp_path):
    repositories, _, promotions = _stack(tmp_path)
    approval_id = _seed_eligible_approval(repositories)
    try:
        promotions.promote(approval_id, "technical_quality_challenger@1.1.0", actor="tester", reason="", confirmation="PROMOTER")
    except StrategyPromotionError as exc:
        assert "Begrunnelse" in str(exc)
    else:
        raise AssertionError("Promotion without reason must fail")


def test_incomplete_binding_transaction_recovers_to_last_active_version(tmp_path):
    repositories, registry, _ = _stack(tmp_path)
    binding = repositories.strategy_production_bindings.get("technical")
    binding.update({
        "state": "PENDING_PROMOTION",
        "pending_version_id": "technical_quality_challenger@1.1.0",
        "version_id": "technical_benchmark@legacy-1.0.0",
    })
    repositories.strategy_production_bindings.upsert(binding)
    target = registry.get("technical_quality_challenger@1.1.0")
    target.update({"status": "PRODUCTION", "execution_mode": "PAPER"})
    repositories.strategy_versions.upsert(target)
    previous = registry.get("technical_benchmark@legacy-1.0.0")
    previous.update({"status": "SHADOW", "execution_mode": "SHADOW_READ_ONLY"})
    repositories.strategy_versions.upsert(previous)

    registry.ensure_defaults()
    recovered = repositories.strategy_production_bindings.get("technical")
    assert recovered["state"] == "ACTIVE"
    assert recovered["pending_version_id"] == ""
    assert registry.production_for_family("technical")["version_id"] == "technical_benchmark@legacy-1.0.0"
    assert registry.get("technical_benchmark@legacy-1.0.0")["status"] == "PRODUCTION"
    assert registry.get("technical_quality_challenger@1.1.0")["status"] == "SHADOW"


def test_evaluation_export_contains_binding_and_promotion_audit(tmp_path):
    import io
    import zipfile
    from services.evaluation_export_service import EvaluationExportService
    from services.strategy_account_service import StrategyAccountService

    repositories, registry, promotions = _stack(tmp_path)
    approval_id = _seed_eligible_approval(repositories)
    promotions.promote(approval_id, "technical_quality_challenger@1.1.0", actor="tester", reason="export test", confirmation="PROMOTER")
    payload = EvaluationExportService(repositories, accounts=StrategyAccountService(repositories, registry)).build_zip()
    with zipfile.ZipFile(io.BytesIO(payload)) as archive:
        names = set(archive.namelist())
        assert "strategy_production_bindings.csv" in names
        assert "strategy_promotions.csv" in names
        assert len(names) == 21
        assert b"technical_quality_challenger@1.1.0" in archive.read("strategy_production_bindings.csv")
        assert b"ACTIVE" in archive.read("strategy_promotions.csv")


def test_scanner_is_routed_through_canonical_production_service():
    from pathlib import Path
    scanner = Path("scanner_worker.py").read_text(encoding="utf-8")
    assert "get_production_strategy_service" in scanner
    assert ".evaluate_technical(" in scanner
    assert "base_decision = build_trading_decision" in scanner
