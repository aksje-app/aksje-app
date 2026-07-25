from datetime import datetime, timedelta, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def _candidate(now, **overrides):
    value = {
        "ticker": "TEST.OL", "source": "Investment Pipeline",
        "data_quality": 82, "confidence_score": 90,
        "status": "ANBEFALT FOR VURDERING",
        "raw": {
            "data_source": "yfinance-live", "data_fetch_status": "OK",
            "fetch_completed_at": now.isoformat(), "refresh_proof": "LIVE_CACHE_BYPASSED",
        },
    }
    value.update(overrides)
    return value


def test_fresh_live_data_is_valid_for_decision():
    from autonomi_core.configuration.policy import AutonomyPolicy
    from autonomi_core.discovery_data.freshness import evaluate_candidate_data

    now = datetime(2026, 7, 22, 10, 0, tzinfo=timezone.utc)
    contract = evaluate_candidate_data(_candidate(now), policy=AutonomyPolicy(), now=now)
    assert contract.source == "yfinance-live"
    assert contract.delivery == "LIVE"
    assert contract.validity == "GYLDIG"
    assert contract.action == "FORTSETT"
    assert contract.valid_for_decision is True


def test_stale_live_data_requires_refetch_and_cannot_recommend():
    from autonomi_core.configuration.policy import AutonomyPolicy
    from autonomi_core.discovery_data.freshness import evaluate_candidate_data

    now = datetime(2026, 7, 22, 10, 0, tzinfo=timezone.utc)
    old = now - timedelta(hours=8)
    contract = evaluate_candidate_data(_candidate(old), policy=AutonomyPolicy(), now=now)
    assert contract.action == "HENT_PÅ_NYTT"
    assert contract.critical_stale is True
    assert contract.valid_for_decision is False


def test_stale_cache_is_visible_fallback_but_not_decision_valid():
    from autonomi_core.configuration.policy import AutonomyPolicy
    from autonomi_core.discovery_data.freshness import evaluate_candidate_data

    now = datetime(2026, 7, 22, 10, 0, tzinfo=timezone.utc)
    old = now - timedelta(hours=8)
    candidate = _candidate(old)
    candidate["raw"].update({"data_source": "yfinance-cache", "refresh_proof": "CACHE_USED", "cache_age_seconds": 28800})
    contract = evaluate_candidate_data(candidate, policy=AutonomyPolicy(), now=now)
    assert contract.action == "BRUK_FALLBACK"
    assert contract.validity == "FALLBACK_MERKET"
    assert contract.valid_for_decision is False


def test_noncritical_missing_data_reduces_confidence():
    from autonomi_core.configuration.policy import AutonomyPolicy
    from autonomi_core.discovery_data.freshness import apply_data_contracts

    now = datetime(2026, 7, 22, 10, 0, tzinfo=timezone.utc)
    candidate = _candidate(now)
    candidate["raw"]["numeric_fields_missing_or_invalid"] = ["pe_ratio"]
    summary = apply_data_contracts([candidate], policy=AutonomyPolicy(), now=now)
    assert candidate["valid_for_decision"] is True
    assert candidate["confidence_score"] == 80
    assert candidate["data_contract"]["action"] == "REDUSER_KONFIDENS"
    assert summary["valid_for_decision"] == 1


def test_weak_or_missing_critical_data_stops_decision():
    from autonomi_core.configuration.policy import AutonomyPolicy
    from autonomi_core.discovery_data.freshness import apply_data_contracts

    now = datetime(2026, 7, 22, 10, 0, tzinfo=timezone.utc)
    candidate = _candidate(now, data_quality=20)
    summary = apply_data_contracts([candidate], policy=AutonomyPolicy(), now=now)
    assert candidate["valid_for_decision"] is False
    assert candidate["status"] == "IKKE ANBEFALT – DATA MÅ FORNYES"
    assert candidate["confidence_score"] == 0
    assert summary["blocked"] == ["TEST.OL"]


def test_no_data_response_is_critical_even_with_timestamp():
    from autonomi_core.configuration.policy import AutonomyPolicy
    from autonomi_core.discovery_data.freshness import evaluate_candidate_data

    now = datetime(2026, 7, 22, 10, 0, tzinfo=timezone.utc)
    candidate = _candidate(now)
    candidate["raw"]["data_fetch_status"] = "NO_DATA"
    candidate["raw"]["data_fetch_error"] = "Ingen markedsdata funnet"
    contract = evaluate_candidate_data(candidate, policy=AutonomyPolicy(), now=now)
    assert contract.action == "STOPP_BESLUTNING"
    assert "kritisk_markedsdata" in contract.missing_data
    assert contract.valid_for_decision is False


def test_autonomy_runtime_filters_invalid_candidates(monkeypatch):
    import autonomous_orchestrator
    from autonomi_core.runtime import orchestrator

    received = {}

    def fake_chain(run, **kwargs):
        received.update(run)
        return {"status": "OK"}

    monkeypatch.setattr(autonomous_orchestrator, "run_post_scan_chain", fake_chain)
    monkeypatch.setattr(orchestrator, "load_policy", lambda: orchestrator.AutonomyPolicy())
    orchestrator.execute_market_mission({
        "run_id": "MI-CONTRACT", "candidates": [
            {"ticker": "OK", "valid_for_decision": True},
            {"ticker": "BLOCK", "valid_for_decision": False},
        ], "proposals": [{"ticker": "BLOCK", "valid_for_decision": False}],
    })
    assert [item["ticker"] for item in received["candidates"]] == ["OK"]
    assert received["proposals"] == [{"ticker": "BLOCK", "valid_for_decision": False, "autonomy_learning_probe": True}]
    assert received["autonomy_learning_probe"] is False
    assert len(received["observed_candidates"]) == 2


def test_release_and_reporting_include_contract():
    version = (ROOT / "app_version.py").read_text(encoding="utf-8")
    source = (ROOT / "market_intelligence.py").read_text(encoding="utf-8")
    assert 'APP_VERSION = "v18.8.' in version
    assert "v18.8.1: Freshness & Data Contract" in version
    assert '"data_contract": data_contract_summary' in source
    assert 'Paragraph("Freshness & Data Contract"' in source
    assert '"Datagyldighet"' in source
