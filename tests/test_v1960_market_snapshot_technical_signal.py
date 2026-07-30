from __future__ import annotations

import json
from pathlib import Path

from app_version import APP_VERSION, get_version_contract
from domain.market_snapshot import validate_candidate_snapshot, validate_market_snapshot
from repositories.application import RepositoryRegistry
from services.market_snapshot_service import MarketSnapshotService
from services.storage_service import StorageService
from services.technical_signal_service import (
    TECHNICAL_SIGNAL_MODEL_VERSION,
    TECHNICAL_SIGNAL_PARAMETER_VERSION,
    TechnicalSignalService,
)


def _service(tmp_path) -> MarketSnapshotService:
    storage = StorageService(base_dir=tmp_path, database_url="", mode="local")
    return MarketSnapshotService(RepositoryRegistry(storage))


def test_version_contract_exposes_snapshot_and_technical_service():
    assert APP_VERSION == "v19.14.6"
    contract = get_version_contract()
    assert contract["market_snapshot_version"] == "1.1"
    assert contract["technical_signal_service_version"] == "1.1"


def test_candidate_snapshot_is_json_serialisable_and_excludes_dataframe(tmp_path):
    service = _service(tmp_path)
    item = {
        "ticker": "EQNR.OL",
        "name": "Equinor",
        "score": 6.0,
        "price": 301.25,
        "hist": object(),
        "forward_pe": 11.4,
        "data_quality": 82,
    }
    snapshot = service.build_candidate_snapshot(
        item,
        {"rsi": 55, "trend": "up", "macd_bullish": True, "breakout_type": "bullish", "channel_pos": 50},
        market_snapshot_id="MS-TEST",
        run_id="RUN-1",
        source="test",
        captured_at="2026-07-26T10:00:00+00:00",
    )
    row = snapshot.to_dict()
    json.dumps(row, ensure_ascii=False)
    assert "hist" not in row["decision_inputs"]
    assert row["market_snapshot_id"] == "MS-TEST"
    assert row["ticker"] == "EQNR.OL"
    assert row["checksum"]
    assert validate_candidate_snapshot(row)["ok"] is True


def test_market_snapshot_uses_one_id_for_all_candidates(tmp_path):
    service = _service(tmp_path)
    snapshot = service.build_market_snapshot(
        [
            {"ticker": "EQNR.OL", "score": 6.0, "price": 300},
            {"ticker": "AIZ", "score": 7.0, "price": 277},
        ],
        run_id="RUN-SHARED",
        source="shared_test",
        captured_at="2026-07-26T10:00:00+00:00",
    )
    row = snapshot.to_dict()
    assert len(row["candidates"]) == 2
    assert {candidate["market_snapshot_id"] for candidate in row["candidates"]} == {row["snapshot_id"]}
    assert validate_market_snapshot(row)["ok"] is True


def test_snapshot_repository_persists_and_rehydrates(tmp_path):
    service = _service(tmp_path)
    snapshot = service.build_market_snapshot(
        [{"ticker": "DNB.OL", "score": 7.1, "price": 250}],
        run_id="RUN-PERSIST",
        source="test",
    )
    saved = service.save(snapshot)
    assert saved["ok"] is True
    recreated = _service(tmp_path)
    loaded = recreated.get(snapshot.snapshot_id)
    assert loaded is not None
    assert loaded["checksum"] == snapshot.checksum
    assert loaded["candidates"][0]["ticker"] == "DNB.OL"


def test_technical_signal_service_preserves_bullish_legacy_result(tmp_path):
    snapshots = _service(tmp_path)
    technical = TechnicalSignalService(snapshots)
    candidate = snapshots.build_candidate_snapshot(
        {"ticker": "EQNR.OL", "score": 6.0, "price": 300},
        {"rsi": 55, "trend": "up", "macd_bullish": True, "breakout_type": "bullish", "channel_pos": 50},
        market_snapshot_id="MS-BULL",
        source="test",
    )
    result = technical.evaluate(candidate)
    assert result["score"] == 8.1
    assert result["risk_score"] == 25
    assert result["decision"] == "BUY"
    assert result["confidence"] == 81
    assert result["market_snapshot_id"] == "MS-BULL"
    assert result["technical_model_version"] == TECHNICAL_SIGNAL_MODEL_VERSION
    assert result["technical_parameter_version"] == TECHNICAL_SIGNAL_PARAMETER_VERSION


def test_technical_signal_service_preserves_bearish_legacy_result(tmp_path):
    snapshots = _service(tmp_path)
    technical = TechnicalSignalService(snapshots)
    result = technical.evaluate(
        {"ticker": "TEST", "score": 6.0, "price": 100},
        {"rsi": 85, "trend": "down", "macd_bullish": False, "breakout_type": "bearish", "channel_pos": 90},
    )
    assert result["score"] == 2.35
    assert result["risk_score"] == 100
    assert result["decision"] == "SELL / AVOID"
    assert result["confidence"] == 35


def test_same_snapshot_produces_deterministic_signal(tmp_path):
    snapshots = _service(tmp_path)
    technical = TechnicalSignalService(snapshots)
    market = snapshots.build_market_snapshot(
        [{"ticker": "AIZ", "score": 7.0, "price": 277, "technical": {"rsi": 55, "trend": "up", "macd_bullish": True}}],
        run_id="RUN-DETERMINISTIC",
        source="test",
    )
    candidate = market.candidates[0]
    first = technical.evaluate(candidate)
    second = technical.evaluate(candidate)
    assert first == second
    assert first["market_snapshot_id"] == market.snapshot_id


def test_signal_engine_is_a_compatibility_facade():
    import signal_engine

    result = signal_engine.score_signal(
        {"ticker": "EQNR.OL", "score": 6.0},
        {"rsi": 55, "trend": "up", "macd_bullish": True, "breakout_type": "bullish", "channel_pos": 50},
    )
    assert result["decision"] == "BUY"
    assert result["technical_signal_schema_version"] == "1.0"
    source = Path(signal_engine.__file__).read_text(encoding="utf-8")
    assert "get_technical_signal_service().evaluate" in source
    assert "score >= 7.2" not in source


def test_scanner_and_autonomy_are_wired_to_canonical_snapshots():
    scanner = Path("scanner_worker.py").read_text(encoding="utf-8")
    autonomy = Path("autonomous_portfolio.py").read_text(encoding="utf-8")
    repositories = Path("repositories/application.py").read_text(encoding="utf-8")
    assert "build_candidate_snapshot" in scanner
    assert 'source="paper_scanner"' in scanner
    assert "candidate_snapshot_id" in scanner
    assert 'source="autonomy_cycle"' in autonomy
    assert "_attach_snapshot_metadata" in autonomy
    assert "market_snapshot_id" in autonomy
    assert "MarketSnapshotRepository" in repositories


def test_service_registry_exposes_shared_services(tmp_path):
    source = Path("services/service_registry.py").read_text(encoding="utf-8")
    assert "self.market_snapshots = MarketSnapshotService" in source
    assert "self.technical_signals = TechnicalSignalService(self.market_snapshots)" in source
