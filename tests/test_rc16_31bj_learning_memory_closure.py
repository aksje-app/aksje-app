from __future__ import annotations

import json
import sys
import types
from datetime import datetime, timezone
from pathlib import Path


def _candidate(ticker: str, blob_size: int = 0):
    return {
        "ticker": ticker,
        "market": "NORGE",
        "sector": "Industrials",
        "strategy": "Growth",
        "current_price": 100.0,
        "investment_score": 75.0,
        "risk_score": 70.0,
        "data_quality_score": 90.0,
        "confidence_score": 80.0,
        "technical_score": 77.0,
        "fundamental_score": 74.0,
        "news_score": 68.0,
        "research_score": 71.0,
        "validation_score": 82.0,
        "portfolio_fit_score": 73.0,
        "valid_for_decision": True,
        "evidence_valid_for_decision": True,
        "autonomy_outcome_code": "KJØPSKANDIDAT",
        "portfolio_action": "KJØP",
        "decision_readiness": {"news": "OK", "insider": "OK"},
        "huge_news_tree": "x" * blob_size,
        "raw": {"current_price": 100.0, "huge_raw": "y" * blob_size},
    }


def test_compact_candidate_drops_heavy_report_trees():
    import learning_observation_engine as engine

    compact = engine._compact_candidate_for_learning(_candidate("AAA.OL", 100_000))
    encoded = json.dumps(compact)
    assert "huge_news_tree" not in compact
    assert "huge_raw" not in compact.get("raw", {})
    assert len(encoded) < 10_000
    assert compact["ticker"] == "AAA.OL"
    assert compact["investment_score"] == 75.0


def test_archive_baseline_loader_keeps_only_compact_runs(monkeypatch):
    import learning_observation_engine as engine

    entries = [
        {"run_id": f"R{i}", "created_at": f"2026-08-{i+1:02d}T08:00:00+00:00"}
        for i in range(6)
    ]
    calls = []

    fake_market = types.ModuleType("market_intelligence")
    fake_market._load_report_archive = lambda: list(reversed(entries))

    def load_archived_run(entry):
        calls.append(entry["run_id"])
        i = int(entry["run_id"][1:])
        return {
            "run_id": entry["run_id"],
            "created_at": entry["created_at"],
            "report_summary": {"production_buy_threshold": 73.0},
            "candidates": [_candidate(f"T{i}A.OL", 250_000), _candidate(f"T{i}B.OL", 250_000)],
            "massive_report_payload": "z" * 500_000,
        }

    fake_market.load_archived_run = load_archived_run
    monkeypatch.setitem(sys.modules, "market_intelligence", fake_market)
    monkeypatch.setattr(engine, "_release_memory", lambda reason: None)
    monkeypatch.setattr(engine, "_breadcrumb", lambda *args, **kwargs: None)

    compact = engine._load_compact_baseline_runs(max_reports=6, max_signals=5)
    assert calls == ["R0", "R1", "R2"]
    assert sum(len(run["candidates"]) for run in compact) == 5
    encoded = json.dumps(compact)
    assert "massive_report_payload" not in encoded
    assert "huge_news_tree" not in encoded
    assert len(encoded) < 50_000


def test_historical_baseline_math_unchanged_for_compact_run():
    import learning_observation_engine as engine

    run = {
        "run_id": "R1",
        "created_at": "2026-08-01T08:00:00+00:00",
        "report_summary": {"production_buy_threshold": 73.0},
        "candidates": [_candidate("AAA.OL")],
    }
    stock = [{"date": "2026-07-31", "close": 100.0}] + [{"date": f"2026-08-{d:02d}", "close": 100.0 + d} for d in range(1, 29)]
    bench = [{"date": "2026-07-31", "close": 200.0}] + [{"date": f"2026-08-{d:02d}", "close": 200.0 + d / 2} for d in range(1, 29)]
    result = engine.build_historical_baseline(
        [engine._compact_run_for_baseline(run, remaining_signals=1500)],
        series_loader=lambda symbols, start: {"AAA.OL": stock, "OSEBX.OL": bench},
        now=datetime(2026, 8, 29, tzinfo=timezone.utc),
    )
    assert result["signal_count"] == 1
    assert result["verified_count"] == 1
    assert result["production_parameters_changed"] is False


def test_bj_source_has_learning_breadcrumbs_and_no_100_run_list_comprehension():
    root = Path(__file__).resolve().parents[1]
    source = (root / "learning_observation_engine.py").read_text(encoding="utf-8")
    version = (root / "app_version.py").read_text(encoding="utf-8")
    assert 'v19.22.0-rc16.31bj: Learning Memory Closure.' in version
    assert 'learning:maintenance:baseline:before' in source
    assert 'learning:baseline:archive_run:before' in source
    assert 'learning:baseline:series_loader:before' in source
    assert 'runs = [load_archived_run(entry) for entry in _load_report_archive()[:100]]' not in source
