from __future__ import annotations

import io
import zipfile
from pathlib import Path

from app_version import APP_VERSION, get_version_contract
from repositories.application import RepositoryRegistry
from services.evaluation_export_service import EvaluationExportService
from services.market_snapshot_service import MarketSnapshotService
from services.parallel_strategy_service import ParallelStrategyService
from services.storage_service import StorageService
from services.strategy_account_service import StrategyAccountService
from services.strategy_lab_service import StrategyLabService
from services.strategy_registry_service import StrategyRegistryService
from services.technical_quality_service import TechnicalQualityService
from services.technical_signal_service import TechnicalSignalService


def _stack(tmp_path):
    storage = StorageService(base_dir=tmp_path, database_url="", mode="local")
    repositories = RepositoryRegistry(storage)
    registry = StrategyRegistryService(repositories)
    registry.ensure_defaults()
    snapshots = MarketSnapshotService(repositories)
    technical = TechnicalSignalService(snapshots)
    quality = TechnicalQualityService(technical)
    parallel = ParallelStrategyService(repositories, registry, technical, quality)
    lab = StrategyLabService(repositories, registry, parallel)
    return repositories, registry, snapshots, parallel, lab


def _candidate(score=6.2, quality=90.0, liquidity=85.0, consensus=80.0, future_return=4.0):
    return {
        "ticker": "EQNR.OL",
        "score": score,
        "scanner_score": score * 10,
        "price": 300.0,
        "data_quality": quality,
        "source_consensus": consensus,
        "liquidity_score": liquidity,
        "insider_score": 80.0,
        "analyst_score": 75.0,
        "earnings_surprise": 12.0,
        "market_regime_score": 70.0,
        "news_score": 65.0,
        "future_return_pct": future_return,
        "technical": {
            "rsi": 55,
            "trend": "up",
            "macd_bullish": True,
            "breakout_type": "bullish",
            "channel_pos": 50,
        },
    }


def _save_snapshots(snapshots, count=4):
    rows = []
    for index in range(count):
        snapshot = snapshots.build_market_snapshot(
            [_candidate(score=6.0 + index * 0.1, future_return=(-2.0 if index == 0 else 3.0 + index))],
            run_id=f"LAB-SNAPSHOT-{index}",
            source="test_v19100",
            captured_at=f"2026-07-{20 + index:02d}T10:00:00+00:00",
        )
        assert snapshots.save(snapshot)["saved"] is True
        rows.append(snapshot)
    return rows


def test_version_contract_exposes_strategy_lab_and_quality_service():
    assert APP_VERSION.startswith("v19.17.0-rc")
    contract = get_version_contract()
    assert contract["technical_quality_service_version"] == "1.1"
    assert contract["strategy_lab_service_version"] == "1.2"
    assert contract["parallel_strategy_service_version"] == "1.1"
    assert contract["evaluation_export_service_version"] == "1.5"


def test_default_quality_challenger_is_read_only(tmp_path):
    _, registry, _, _, _ = _stack(tmp_path)
    challenger = registry.get("technical_quality_challenger@1.1.0")
    assert challenger is not None
    assert challenger["status"] == "CHALLENGER"
    assert challenger["execution_mode"] == "SHADOW_READ_ONLY"
    assert challenger["parent_version_id"] == "technical_quality_challenger@1.0.0"
    assert challenger["metadata"]["production_applied"] is False


def test_low_quality_blocks_challenger_without_changing_benchmark(tmp_path):
    _, _, snapshots, parallel, _ = _stack(tmp_path)
    snapshot = snapshots.build_market_snapshot(
        [_candidate(score=7.0, quality=30.0, liquidity=20.0, consensus=25.0)],
        run_id="QUALITY-BLOCK",
        source="test_v19100",
        captured_at="2026-07-26T10:00:00+00:00",
    )
    result = parallel.evaluate_snapshot(
        snapshot,
        families=["technical"],
        version_ids=["technical_benchmark@legacy-1.0.0", "technical_quality_challenger@1.1.0"],
    )
    by_id = {row["strategy_version_id"]: row for row in result["decisions"]}
    benchmark = by_id["technical_benchmark@legacy-1.0.0"]
    challenger = by_id["technical_quality_challenger@1.1.0"]
    assert benchmark["action"] == "BUY"
    assert challenger["action"] == "AVOID"
    assert challenger["execution_authorized"] is False
    assert challenger["metadata"]["quality_blockers"]
    assert benchmark["metadata"].get("technical_quality_result") is None


def test_quality_evidence_can_promote_only_the_challenger(tmp_path):
    _, _, snapshots, parallel, _ = _stack(tmp_path)
    snapshot = snapshots.build_market_snapshot(
        [_candidate(score=5.0, quality=95.0, liquidity=95.0, consensus=95.0)],
        run_id="QUALITY-SUPPORT",
        source="test_v19100",
        captured_at="2026-07-26T11:00:00+00:00",
    )
    result = parallel.evaluate_snapshot(
        snapshot,
        families=["technical"],
        version_ids=["technical_benchmark@legacy-1.0.0", "technical_quality_challenger@1.1.0"],
    )
    by_id = {row["strategy_version_id"]: row for row in result["decisions"]}
    benchmark = by_id["technical_benchmark@legacy-1.0.0"]
    challenger = by_id["technical_quality_challenger@1.1.0"]
    assert challenger["score"] >= benchmark["score"]
    assert challenger["metadata"]["quality_adjustment"] > 0
    assert all(row["execution_authorized"] is False for row in result["decisions"])


def test_strategy_lab_replay_is_time_ordered_persistent_and_read_only(tmp_path):
    repositories, registry, snapshots, _, lab = _stack(tmp_path)
    saved = _save_snapshots(snapshots, count=4)
    experiment = lab.create_experiment(
        name="Quality replay",
        hypothesis="Quality filter improves selection",
        baseline_version_id="technical_benchmark@legacy-1.0.0",
        challenger_version_ids=["technical_quality_challenger@1.1.0"],
        snapshot_ids=[row.snapshot_id for row in saved],
        mode="WALK_FORWARD",
        train_ratio=0.5,
        actor="tester",
    )
    result = lab.run_experiment(experiment["experiment_id"], actor="tester")
    assert result["snapshot_count"] == 4
    assert result["split"]["train_snapshots"] == 2
    assert result["split"]["validation_snapshots"] == 2
    assert result["production_applied"] is False
    assert result["execution_authorized"] is False
    assert {row["strategy_version_id"] for row in result["metrics"]} == {
        "technical_benchmark@legacy-1.0.0",
        "technical_quality_challenger@1.1.0",
    }
    assert all(row["execution_authorized"] is False for row in result["decisions"])
    repositories2 = RepositoryRegistry(StorageService(base_dir=tmp_path, database_url="", mode="local"))
    assert repositories2.strategy_lab_runs.get(result["lab_run_id"])["decision_count"] == result["decision_count"]
    assert registry.production_for_family("technical")["version_id"] == "technical_benchmark@legacy-1.0.0"


def test_lab_approval_and_rollback_never_promote(tmp_path):
    _, registry, snapshots, _, lab = _stack(tmp_path)
    saved = _save_snapshots(snapshots, count=2)
    experiment = lab.create_experiment(
        name="Approval test",
        hypothesis="Manual review only",
        baseline_version_id="technical_benchmark@legacy-1.0.0",
        challenger_version_ids=["technical_quality_challenger@1.1.0"],
        snapshot_ids=[row.snapshot_id for row in saved],
        actor="tester",
    )
    lab.run_experiment(experiment["experiment_id"], actor="tester")
    lab.submit_review(experiment["experiment_id"], actor="tester", reason="review")
    approval = lab.approve(experiment["experiment_id"], actor="tester", reason="good result", confirmation="GODKJENN")
    assert approval["production_applied"] is False
    assert approval["automatic_promotion"] is False
    assert registry.production_for_family("technical")["version_id"] == "technical_benchmark@legacy-1.0.0"
    rolled = lab.rollback_approval(approval["approval_id"], actor="tester", reason="more data needed", confirmation="RULL TILBAKE")
    assert rolled["status"] == "ROLLED_BACK"
    assert rolled["production_applied"] is False


def test_evaluation_zip_contains_strategy_lab_and_quality_results(tmp_path):
    repositories, _, snapshots, parallel, lab = _stack(tmp_path)
    saved = _save_snapshots(snapshots, count=2)
    experiment = lab.create_experiment(
        name="Export lab",
        hypothesis="Export comparable evidence",
        baseline_version_id="technical_benchmark@legacy-1.0.0",
        challenger_version_ids=["technical_quality_challenger@1.1.0"],
        snapshot_ids=[row.snapshot_id for row in saved],
        actor="tester",
    )
    lab.run_experiment(experiment["experiment_id"], actor="tester")
    accounts = StrategyAccountService(repositories, StrategyRegistryService(repositories))
    export = EvaluationExportService(repositories, accounts=accounts)
    payload = export.build_zip(additional_metadata={"authorization": "Bearer synthetic-secret-for-redaction"})
    with zipfile.ZipFile(io.BytesIO(payload)) as archive:
        names = set(archive.namelist())
        assert "technical_quality_challenger.csv" in names
        assert "strategy_lab_experiments.csv" in names
        assert "strategy_lab_runs.csv" in names
        assert "strategy_lab_approvals.csv" in names
        assert "quality_diagnostics.csv" in names
        assert "result_attribution.csv" in names
        assert len(names) == 21
        manifest = archive.read("manifest.json").decode("utf-8")
        metadata = archive.read("run_metadata.json").decode("utf-8")
        assert '"contains_secrets": false' in manifest
        assert "synthetic-secret-for-redaction" not in metadata


def test_strategy_lab_workspace_is_visible_and_production_engine_is_unchanged():
    autonomy_page = Path("pages/autonomy.py").read_text(encoding="utf-8")
    lab_page = Path("pages/strategy_lab.py").read_text(encoding="utf-8")
    parallel = Path("services/parallel_strategy_service.py").read_text(encoding="utf-8")
    assert '"strategy_lab": "Strategy Lab"' in autonomy_page
    assert "render_strategy_lab" in autonomy_page
    assert "Automatisk promotering" in lab_page
    assert "version_ids" in parallel
    assert "execution_authorized=False" in parallel
