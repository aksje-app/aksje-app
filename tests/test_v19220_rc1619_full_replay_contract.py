from __future__ import annotations

import copy

import pytest

import replay_contract as contract
import report_replay_export as export


def _context():
    return {
        "portfolio_status": "ACTIVE",
        "positions": [],
        "position_count": 0,
        "cash": 100000.0,
        "total_value": 100000.0,
        "cash_pct": 100.0,
        "sector_exposure": {},
        "country_exposure": {},
        "currency_exposure": {},
        "limits": {
            "max_position_pct": 10.0,
            "max_sector_pct": 25.0,
            "max_positions": 12,
            "min_cash_pct": 15.0,
            "max_pair_correlation": 0.85,
        },
        "max_country_pct": 45.0,
        "max_currency_pct": 55.0,
        "minimum_liquidity_score": 40.0,
        "maximum_candidate_risk_score": 75.0,
        "minimum_investment_score": 78.0,
        "minimum_data_quality": 55.0,
        "allow_additions": False,
        "source": "test",
    }


def _candidate():
    return {
        "ticker": "TEST",
        "market": "USA",
        "sector": "Technology",
        "price": 100.0,
        "investment_score": 82.0,
        "risk_score": 30.0,
        "liquidity_score": 80.0,
        "data_quality": 90.0,
        "valid_for_decision": True,
        "evidence_valid_for_decision": True,
        "mission_eligible": True,
        "strategy_matches": ["Quality"],
        "proposed_position_pct": 1.0,
        "raw": {"source_provenance": {"price": "snapshot"}},
    }


def _bundle():
    before = {"status": "ACTIVE", "cash": 100000.0, "positions": {}}
    after = {"status": "ACTIVE", "cash": 99000.0, "positions": {"TEST": {"quantity": 10, "average_price": 100.0}}}
    action = {"run_id": "RUN-1", "action": "BUY", "ticker": "TEST", "value": 1000.0}
    return contract.build_snapshot(
        run_id="RUN-1",
        candidates=[_candidate()],
        portfolio_before=before,
        portfolio_after=after,
        portfolio_context=_context(),
        parameters={"minimum_investment_score": 78.0},
        market_snapshot={"snapshot_id": "SNAP-1", "candidates": [_candidate()]},
        actions=[action],
    )


def test_full_replay_requires_successful_offline_rerun_and_reconciliation():
    bundle = _bundle()
    assert bundle["manifest"]["replay_level"] == "FULL_REPLAY"
    audit = contract.audit_snapshot(bundle)
    assert audit["ok"] is True
    assert audit["decision_replay_verified"] is True
    assert audit["portfolio_reconciliation_verified"] is True


def test_tampered_snapshot_is_rejected():
    bundle = _bundle()
    bundle["files"]["candidates_input.json"][0]["investment_score"] = 1.0
    audit = contract.audit_snapshot(bundle)
    assert audit["ok"] is False
    assert "CHECKSUM_MISMATCH:candidates_input.json" in audit["errors"]


def test_missing_raw_input_never_receives_full_replay():
    candidate = _candidate()
    candidate.pop("liquidity_score")
    bundle = _bundle()
    bundle["files"]["candidates_input.json"] = [candidate]
    bundle["manifest"]["hashes"]["candidates_input.json"] = contract._sha256(contract._stable_bytes([candidate]))
    audit = contract.audit_snapshot(bundle, rerun=False)
    assert audit["ok"] is False
    assert "CANDIDATE_FIELD_MISSING:0:liquidity_score" in audit["errors"]


def test_inconsistent_buy_and_sell_is_rejected():
    bundle = _bundle()
    actions = bundle["files"]["actions.json"]
    actions.append({"run_id": "RUN-1", "action": "SELL", "ticker": "TEST", "value": 1000.0})
    bundle["manifest"]["hashes"]["actions.json"] = contract._sha256(contract._stable_bytes(actions))
    audit = contract.audit_snapshot(bundle, rerun=False)
    assert "SAME_TICKER_BOUGHT_AND_SOLD" in audit["errors"]


def test_persistence_is_immutable_and_idempotent(tmp_path, monkeypatch):
    monkeypatch.setattr(contract, "ROOT", tmp_path)
    durable = {}
    monkeypatch.setattr(contract, "durable_read_json", lambda key, path, default: copy.deepcopy(durable.get(key, default)))
    monkeypatch.setattr(contract, "durable_write_json", lambda key, path, value: (durable.__setitem__(key, copy.deepcopy(value)), path.parent.mkdir(parents=True, exist_ok=True), path.write_text(contract._stable_bytes(value).decode("utf-8"), encoding="utf-8")))
    bundle = _bundle()
    first = contract.persist_snapshot(bundle)
    second = contract.persist_snapshot(bundle)
    assert first["stored"] is True
    assert second["reused"] is True

    changed = copy.deepcopy(bundle)
    changed["files"]["portfolio_after.json"]["cash"] = 1.0
    changed["manifest"]["hashes"]["portfolio_after.json"] = contract._sha256(
        contract._stable_bytes(changed["files"]["portfolio_after.json"])
    )
    with pytest.raises(RuntimeError, match="uforanderlig"):
        contract.persist_snapshot(changed)


def test_export_inventory_is_committed_only_from_verified_summary(monkeypatch):
    stored = {}
    monkeypatch.setattr(export, "_load_export_inventory", lambda: copy.deepcopy(stored))
    monkeypatch.setattr(export, "durable_write_json", lambda key, path, value: stored.update(copy.deepcopy(value)))
    unchanged = export.commit_export_inventory({"exported_at": "2026-08-06T00:00:00Z"})
    assert unchanged == {}
    result = export.commit_export_inventory({
        "exported_at": "2026-08-06T00:00:00Z",
        "export_type": "BASELINE_REPLAY_ARCHIVE",
        "inventory_updates": {"MI-1": {"content_sha256": "abc", "status": "EXPORTED", "replay_level": "FULL_REPLAY"}},
    })
    assert result["reports"]["MI-1"]["content_sha256"] == "abc"
