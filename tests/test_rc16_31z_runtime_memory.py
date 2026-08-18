import json

from market_intelligence import compact_market_run_for_report
from runtime_memory import memory_snapshot, release_process_memory


def _large_candidate(ticker: str) -> dict:
    return {
        "ticker": ticker,
        "market": "USA",
        "status": "OBSERVASJONSLISTE",
        "portfolio_action": "SKIP",
        "investment_score": 71.5,
        "confidence_score": 68.0,
        "risk_score": 42.0,
        "valid_for_decision": True,
        "evidence_valid_for_decision": False,
        "raw": {
            "provider_payload": "x" * 250_000,
            "news_intelligence": {"events": [{"body": "y" * 100_000}]},
        },
        "selection_trace": [{"detail": "z" * 50_000}],
    }


def test_compact_market_run_removes_duplicate_raw_evidence_but_keeps_audit_truth():
    candidate = _large_candidate("AAA")
    source = {
        "version": "test", "summary": {"scanned": 59},
        "universe_contract": {"configured_universe": 59},
        "selection_trace": [{"raw": "q" * 500_000}],
        "candidates": [candidate], "proposals": [candidate.copy()],
    }
    compact = compact_market_run_for_report(source)
    assert compact["candidate_count"] == 1
    assert compact["proposal_count"] == 1
    assert compact["candidates"][0]["portfolio_action"] == "SKIP"
    assert "raw" not in compact["candidates"][0]
    assert "selection_trace" not in compact
    assert len(json.dumps(compact)) < len(json.dumps(source)) / 20


def test_memory_snapshot_exposes_current_rss_and_cleanup_is_repeatable():
    snapshot = memory_snapshot()
    assert snapshot["process_pid"] > 0
    assert snapshot.get("process_rss_mb", 0) > 0
    first = release_process_memory("test-1")
    second = release_process_memory("test-2")
    assert first["reason"] == "test-1"
    assert second["reason"] == "test-2"
    assert "after" in first and "process_rss_mb" in first["after"]
