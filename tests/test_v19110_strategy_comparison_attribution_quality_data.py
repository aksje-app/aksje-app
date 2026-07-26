from __future__ import annotations

import io
import os
import zipfile

import pandas as pd

from repositories.application import RepositoryRegistry
from services.evaluation_export_service import EvaluationExportService
from services.market_snapshot_service import MarketSnapshotService
from services.paper_quality_enrichment_service import PaperQualityEnrichmentService
from services.parallel_strategy_service import ParallelStrategyService
from services.quality_evidence_normalizer import liquidity_score_from_turnover, normalize_score
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


def _candidate(ticker: str, *, quality=None, liquidity=None, consensus=None, future_return=0.0):
    row = {
        "ticker": ticker,
        "score": 7.0,
        "scanner_score": 70.0,
        "price": 100.0,
        "future_return_pct": future_return,
        "technical": {"rsi": 55, "trend": "up", "macd_bullish": True, "breakout_type": "bullish", "channel_pos": 50},
    }
    if quality is not None:
        row["data_quality"] = quality
    if liquidity is not None:
        row["liquidity_score"] = liquidity
    if consensus is not None:
        row["source_consensus"] = consensus
    return row


def test_quality_normalizer_handles_fraction_and_rejects_raw_volume():
    fraction = normalize_score(0.82, source="test")
    assert fraction["value"] == 82.0
    assert "fraction_0_1" in fraction["normalised_from"]
    raw_volume = normalize_score(500000, source="raw_volume")
    assert raw_volume["status"] == "INVALID"
    liquidity = liquidity_score_from_turnover(average_volume=100000, price=100)
    assert liquidity["status"] == "AVAILABLE"
    assert 0 <= liquidity["value"] <= 100


def test_missing_data_is_not_below_threshold(tmp_path):
    _, _, snapshots, parallel, _ = _stack(tmp_path)
    snapshot = snapshots.build_market_snapshot([_candidate("MISS.OL")], run_id="MISSING", source="test")
    result = parallel.evaluate_snapshot(snapshot, families=["technical"], version_ids=["technical_quality_challenger@1.1.0"])
    row = result["decisions"][0]
    quality = row["metadata"]["technical_quality_result"]
    assert row["action"] == "HOLD"
    assert quality["quality_evidence_sufficient"] is False
    assert quality["quality_blockers"] == []
    assert "data_quality" in quality["quality_missing_components"]
    assert any("MANGLER DATA" in warning for warning in quality["warnings"])


def test_below_threshold_has_explicit_blocker_code(tmp_path):
    _, _, snapshots, parallel, _ = _stack(tmp_path)
    snapshot = snapshots.build_market_snapshot(
        [_candidate("LOW.OL", quality=30, liquidity=20, consensus=25)], run_id="LOW", source="test"
    )
    result = parallel.evaluate_snapshot(snapshot, families=["technical"], version_ids=["technical_quality_challenger@1.1.0"])
    row = result["decisions"][0]
    quality = row["metadata"]["technical_quality_result"]
    assert row["action"] == "AVOID"
    assert "DATA_QUALITY_BELOW_THRESHOLD" in quality["quality_blocker_codes"]
    assert "LIQUIDITY_BELOW_THRESHOLD" in quality["quality_blocker_codes"]
    assert "SOURCE_CONSENSUS_BELOW_THRESHOLD" in quality["quality_blocker_codes"]
    assert not {"data_quality", "liquidity", "source_consensus"}.intersection(quality["quality_missing_components"])


def test_paper_enrichment_preserves_score_and_builds_normalised_evidence(monkeypatch):
    monkeypatch.setenv("PAPER_QUALITY_FETCH_NEWS", "false")
    monkeypatch.setenv("PAPER_QUALITY_FETCH_INSIDER", "false")
    index = pd.date_range("2026-01-01", periods=260, freq="B", tz="UTC")
    hist = pd.DataFrame({"Close": [100 + i * 0.1 for i in range(260)], "Volume": [100000] * 260}, index=index)
    item = {
        "ticker": "EQNR.OL", "score": 6.4, "price": 125.0, "hist": hist,
        "volatility": 0.2, "max_drawdown": -0.1, "market_cap": 1000000000,
        "profit_margin": 0.1, "revenue_growth": 0.05, "debt_to_equity": 40,
    }
    enriched = PaperQualityEnrichmentService().enrich(item, {"trend": "up"})
    assert enriched["score"] == 6.4
    assert 0 <= enriched["liquidity_score"] <= 100
    assert enriched["liquidity_score"] != 100000
    assert enriched["quality_evidence"]["news_score"]["status"] == "MISSING"
    assert enriched["quality_coverage"]["available_critical_components"] >= 2
    assert enriched["quality_enrichment"]["production_score_unchanged"] is True



def test_paper_enrichment_does_not_change_production_technical_decision(tmp_path, monkeypatch):
    monkeypatch.setenv("PAPER_QUALITY_FETCH_NEWS", "false")
    monkeypatch.setenv("PAPER_QUALITY_FETCH_INSIDER", "false")
    index = pd.date_range("2025-01-01", periods=260, freq="B", tz="UTC")
    hist = pd.DataFrame({"Close": [100 + i * 0.2 for i in range(260)], "Volume": [150000] * 260}, index=index)
    item = {
        "ticker": "PARITY.OL", "score": 6.4, "price": 151.8, "hist": hist,
        "volatility": 0.2, "max_drawdown": -0.1, "market_cap": 1_000_000_000,
    }
    repositories, _, snapshots, _, _ = _stack(tmp_path)
    technical = TechnicalSignalService(snapshots)
    context = {"rsi": 55, "trend": "up", "macd_bullish": True, "breakout_type": "bullish", "channel_pos": 50}
    before = snapshots.build_candidate_snapshot(item, context, run_id="BEFORE", source="test")
    enriched = PaperQualityEnrichmentService().enrich(item, context)
    after = snapshots.build_candidate_snapshot(enriched, context, run_id="AFTER", source="test")
    before_result = technical.evaluate(before)
    after_result = technical.evaluate(after)
    assert before_result["decision"] == after_result["decision"]
    assert before_result["score"] == after_result["score"]
    assert enriched["quality_enrichment"]["production_decision_unchanged"] is True

def test_snapshot_never_uses_average_volume_as_liquidity_score(tmp_path):
    _, _, snapshots, _, _ = _stack(tmp_path)
    candidate = snapshots.build_candidate_snapshot(
        {"ticker": "VOL.OL", "score": 6, "price": 100, "average_volume": 900000},
        {"trend": "up"}, run_id="RAWVOL", source="test",
    )
    assert candidate.liquidity is None


def test_strategy_lab_aggregates_diagnostics_and_attributes_avoided_loss(tmp_path):
    repositories, _, snapshots, _, lab = _stack(tmp_path)
    rows = [
        _candidate("LOSS.OL", quality=20, liquidity=20, consensus=20, future_return=-8.0),
        _candidate("WIN.OL", quality=90, liquidity=90, consensus=90, future_return=6.0),
        _candidate("MISSING.OL", future_return=2.0),
    ]
    saved = []
    for i, row in enumerate(rows):
        snapshot = snapshots.build_market_snapshot([row], run_id=f"ATTR-{i}", source="test", captured_at=f"2026-07-{20+i:02d}T10:00:00+00:00")
        snapshots.save(snapshot)
        saved.append(snapshot.snapshot_id)
    experiment = lab.create_experiment(
        name="Attribution", hypothesis="Filter weak evidence", baseline_version_id="technical_benchmark@legacy-1.0.0",
        challenger_version_ids=["technical_quality_challenger@1.1.0"], snapshot_ids=saved, train_ratio=0.67, actor="tester",
    )
    result = lab.run_experiment(experiment["experiment_id"], actor="tester")
    diagnostics = result["quality_diagnostics"]
    assert diagnostics["quality_decisions"] == 3
    assert diagnostics["sufficient_evidence_count"] == 2
    assert diagnostics["insufficient_evidence_count"] == 1
    component = {row["component"]: row for row in diagnostics["components"]}
    assert component["data_quality"]["below_threshold"] == 1
    assert component["data_quality"]["missing"] == 1
    attribution = result["result_attribution"][0]
    assert attribution["baseline_buys_filtered"] == 2
    assert attribution["avoided_losses"] == 1
    assert attribution["missed_gains"] == 1
    assert attribution["outcome_pairs"] == 3
    assert attribution["attribution_reliable"] is False
    assert repositories.strategy_lab_runs.get(result["lab_run_id"])["quality_diagnostics"] == diagnostics


def test_export_contains_diagnostics_and_attribution(tmp_path):
    repositories, _, snapshots, _, lab = _stack(tmp_path)
    snapshot = snapshots.build_market_snapshot(
        [_candidate("EXP.OL", quality=20, liquidity=20, consensus=20, future_return=-3)], run_id="EXP", source="test"
    )
    snapshots.save(snapshot)
    experiment = lab.create_experiment(
        name="Export", hypothesis="Export attribution", baseline_version_id="technical_benchmark@legacy-1.0.0",
        challenger_version_ids=["technical_quality_challenger@1.1.0"], snapshot_ids=[snapshot.snapshot_id], actor="tester",
    )
    lab.run_experiment(experiment["experiment_id"], actor="tester")
    export = EvaluationExportService(repositories, accounts=StrategyAccountService(repositories, StrategyRegistryService(repositories)))
    payload = export.build_zip()
    with zipfile.ZipFile(io.BytesIO(payload)) as archive:
        names = set(archive.namelist())
        assert len(names) == 21
        assert "quality_diagnostics.csv" in names
        assert "result_attribution.csv" in names
        assert "strategy_outcomes.csv" in names
        assert b"DATA_QUALITY_BELOW_THRESHOLD" in archive.read("quality_diagnostics.csv")
        assert b"avoided_losses" in archive.read("result_attribution.csv")


def test_strategy_lab_ui_exposes_diagnostics_and_attribution():
    text = open("pages/strategy_lab.py", encoding="utf-8").read()
    assert "Datadekning og blokkårsaker" in text
    assert "MANGLER DATA" in text
    assert "Resultatattribusjon" in text
    assert "unngått" not in text.lower() or "avoided_losses" not in text  # UI uses stable metric fields from service.


def test_strategy_outcomes_are_observed_separately_and_idempotent(tmp_path):
    from services.strategy_outcome_service import StrategyOutcomeService

    repositories, registry, snapshots, parallel, _ = _stack(tmp_path)
    snapshot = snapshots.build_market_snapshot(
        [_candidate("OBS.OL", quality=20, liquidity=20, consensus=20)],
        run_id="OBSERVED",
        source="test",
        captured_at="2026-07-01T10:00:00+00:00",
    )
    snapshots.save(snapshot)
    immutable_before = snapshot.to_dict()
    dates = pd.date_range("2026-07-02", periods=25, freq="B", tz="UTC")
    history = pd.DataFrame({"Close": [101.0 + i for i in range(25)]}, index=dates)
    outcomes = StrategyOutcomeService(repositories, history_provider=lambda ticker: history)

    first = outcomes.settle_snapshots([snapshot.to_dict()])
    second = outcomes.settle_snapshots([snapshot.to_dict()])

    assert first["created"] == 3
    assert second["existing"] == 3
    assert snapshot.to_dict() == immutable_before
    assert snapshots.get(snapshot.snapshot_id) == immutable_before
    candidate_id = snapshot.candidates[0]["candidate_snapshot_id"]
    assert outcomes.outcome_for(candidate_id, horizon=1)["return_pct"] == 1.0
    assert outcomes.outcome_for(candidate_id, horizon=5)["return_pct"] == 5.0
    assert outcomes.outcome_for(candidate_id, horizon=20)["return_pct"] == 20.0
    assert all(row["lookahead_used_in_decision"] is False for row in repositories.strategy_outcomes.list())


def test_strategy_lab_uses_observed_outcome_ledger_without_snapshot_lookahead(tmp_path):
    from services.strategy_outcome_service import StrategyOutcomeService

    repositories, registry, snapshots, parallel, _ = _stack(tmp_path)
    snapshot = snapshots.build_market_snapshot(
        [_candidate("LEDGER.OL", quality=20, liquidity=20, consensus=20, future_return=None)],
        run_id="LEDGER",
        source="test",
        captured_at="2026-07-01T10:00:00+00:00",
    )
    snapshots.save(snapshot)
    dates = pd.date_range("2026-07-02", periods=25, freq="B", tz="UTC")
    history = pd.DataFrame({"Close": [99.0, 98.0, 97.0, 96.0, 90.0] + [90.0] * 20}, index=dates)
    outcomes = StrategyOutcomeService(repositories, history_provider=lambda ticker: history)
    lab = StrategyLabService(repositories, registry, parallel, outcomes)
    experiment = lab.create_experiment(
        name="Observed attribution",
        hypothesis="Quality filter avoids observed loss",
        baseline_version_id="technical_benchmark@legacy-1.0.0",
        challenger_version_ids=["technical_quality_challenger@1.1.0"],
        snapshot_ids=[snapshot.snapshot_id],
        actor="tester",
    )

    result = lab.run_experiment(experiment["experiment_id"], actor="tester", settle_outcomes=True)

    attribution = result["result_attribution"][0]
    assert result["outcome_settlement"]["created"] == 3
    assert result["outcome_coverage"]["observed_candidates"] == 1
    assert result["outcome_coverage"]["primary_horizon_sessions"] == 5
    assert attribution["outcome_pairs"] == 1
    assert attribution["avoided_losses"] == 1
    assert attribution["filtered_average_return_pct"] == -10.0
    saved_snapshot = snapshots.get(snapshot.snapshot_id)
    assert "future_return_pct" not in saved_snapshot["candidates"][0].get("decision_inputs", {}) or saved_snapshot["candidates"][0]["decision_inputs"].get("future_return_pct") is None
    assert result["metadata"]["lookahead_used"] is False
