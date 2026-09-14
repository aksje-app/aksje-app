from datetime import datetime, timezone
from types import SimpleNamespace
from io import BytesIO

from pypdf import PdfReader


def _candidate(ticker, score, *, outcome="MODERAT_KJØPSANBEFALING", ready=False):
    return {
        "ticker": ticker, "market": "Norge", "investment_score": score,
        "autonomy_outcome_code": outcome,
        "portfolio_action": "BUY" if outcome == "KJØPSKANDIDAT" else "REVIEW",
        "valid_for_decision": True,
        "evidence_valid_for_decision": bool(ready),
        "final_decision_ready": bool(ready),
        "source_consensus": {"independent_sources": 2 if ready else 0},
    }


def test_dual_ranking_keeps_analysis_separate_from_buy_ready(monkeypatch):
    import candidate_actionability as module
    monkeypatch.setattr(module, "load_passports", lambda: {})
    run = {"run_id": "MI-BA-1", "created_at": "2026-09-03T12:00:00+00:00", "candidates": [
        _candidate("NORAM.OL", 79.59),
        _candidate("READY.OL", 78.4, outcome="KJØPSKANDIDAT", ready=True),
    ]}
    result = module.build_actionability(run)
    assert result["analysis_top3"][0]["ticker"] == "NORAM.OL"
    assert result["analysis_top3"][0]["status"] == "BLOKKERT"
    assert result["buy_ready_top3"][0]["ticker"] == "READY.OL"
    assert run["candidates"][0]["trade_authority_label"] == "NEI"
    assert "INVALID_EVIDENCE" in run["candidates"][0]["actionability"]["blocker_codes"]


def test_repeated_top_candidate_becomes_stalled_evidence(monkeypatch):
    import candidate_actionability as module
    monkeypatch.setattr(module, "load_passports", lambda: {"NORAM.OL": [
        {"report_id": "A", "created_at": "2026-09-02T08:00:00+00:00", "buy_ready": False},
        {"report_id": "B", "created_at": "2026-09-02T14:00:00+00:00", "buy_ready": False},
    ]})
    run = {"run_id": "C", "created_at": "2026-09-03T08:00:00+00:00", "candidates": [_candidate("NORAM.OL", 80)]}
    module.build_actionability(run)
    state = run["candidates"][0]["actionability"]
    assert state["execution_status"] == "STALLED_EVIDENCE"
    assert state["evidence_priority"] == "KRITISK"
    assert state["blocked_report_count"] == 3


def test_stalled_top_candidate_is_carried_into_next_evidence_budget(monkeypatch):
    import candidate_actionability as module
    monkeypatch.setattr(module, "load_passports", lambda: {
        "NORAM.OL": [
            {"created_at": "2026-09-02T08:00:00+00:00", "analysis_rank": 1, "buy_ready": False},
            {"created_at": "2026-09-02T14:00:00+00:00", "analysis_rank": 1, "buy_ready": False},
        ],
        "OLD.OL": [{"created_at": "2026-09-01T08:00:00+00:00", "analysis_rank": 8, "buy_ready": False}],
    })
    assert module.evidence_priority_tickers() == ["NORAM.OL"]


def test_degraded_learning_is_not_reported_as_engine_failure(monkeypatch):
    import learning_observation_engine as engine
    analysis = {
        "active_count": 78, "matured_count": 0,
        "horizons": [
            {"horizon_days": 1, "return": {"count": 77}},
            {"horizon_days": 5, "return": {"count": 0}},
            {"horizon_days": 20, "return": {"count": 0}, "excess_return": {"count": 0, "average": None}},
            {"horizon_days": 60, "return": {"count": 0}},
        ],
        "health": {"status": "DEGRADED", "missing_or_stale": 1, "missing_tickers": ["MISS.OL"],
                   "benchmark_mapping_complete": True},
        "selection_quality": {"status": "FOR LITE DATA"},
    }
    monkeypatch.setattr(engine, "build_weekly_analysis", lambda now=None: analysis)
    monkeypatch.setattr(engine, "load_engine_state", lambda: {"daily": {"status": "DEGRADED", "completed_at": "2026-09-03T01:00:00+00:00"}})
    monkeypatch.setattr(engine, "read_json", lambda *args, **kwargs: {})
    result = engine.report_control_snapshot(now=datetime(2026, 9, 3, tzinfo=timezone.utc))
    assert result["status"] == "DEGRADERT"
    assert result["health_detail"]["affected_tickers"] == ["MISS.OL"]
    assert result["health_detail"]["partial_results_preserved"] is True


def test_selection_control_exposes_missed_value_without_changing_production():
    import learning_observation_engine as engine
    rows = []
    for index in range(10):
        rows.append({"ticker": f"S{index}", "group": "MODERATE", "status": "ACTIVE",
                     "decision_snapshot": {"score": 75 + index},
                     "horizon_measurements": {"20": {"return_pct": 0, "benchmark_return_pct": 1, "excess_return_pct": -1}}})
        rows.append({"ticker": f"C{index}", "group": "MATCHED_CONTROL", "status": "ACTIVE",
                     "decision_snapshot": {"score": 65 + index},
                     "horizon_measurements": {"20": {"return_pct": 3, "benchmark_return_pct": 1, "excess_return_pct": 2}}})
    result = engine.build_weekly_analysis(rows)
    quality = result["selection_quality"]
    assert quality["status"] == "INGEN DOKUMENTERT MERVERDI"
    assert quality["value_alarm"] is True
    assert quality["selected_minus_control_pct_points"] == -3
    assert quality["production_changed"] is False


def test_same_run_roundtrip_survives_process_memory_reset(monkeypatch):
    import paper_trading_guard as guard
    stored = {}
    monkeypatch.setattr(guard, "read_json", lambda *args, **kwargs: stored.copy())
    def write(_key, _path, value):
        stored.clear(); stored.update(value)
    monkeypatch.setattr(guard, "write_json", write)
    monkeypatch.setattr(guard, "paper_trading_decision", lambda: SimpleNamespace(allowed=True, code="OK", reason=""))
    guard._RUN_ACTIONS.clear()
    guard.record_paper_trade("SELL", ticker="FRO.OL", run_id="RUN-1")
    guard._RUN_ACTIONS.clear()  # simulate a new Render process
    result = guard.check_paper_trade("BUY", ticker="FRO.OL", run_id="RUN-1")
    assert result.allowed is False
    assert result.code == "SAME_RUN_ROUNDTRIP"


def test_pdf_names_analysis_and_buy_ready_as_separate_lists():
    import market_intelligence as market
    run = {
        "run_id": "MI-BA-PDF", "created_at": "2026-09-03T12:00:00+00:00",
        "job_name": "Morgenanalyse", "trigger": "SCHEDULED", "markets": ["Norge"],
        "summary": {}, "candidates": [_candidate("NORAM.OL", 79.59)], "changes": {}, "data_refresh": {},
        "candidate_actionability": {
            "analysis_top3": [{"ticker": "NORAM.OL", "score": 79.59, "status": "BLOKKERT",
                               "blocker_codes": ["INVALID_EVIDENCE"]}],
            "buy_ready_top3": [], "buy_ready_count": 0,
        },
    }
    text = "\n".join(page.extract_text() or "" for page in PdfReader(BytesIO(market.build_pdf(run))).pages)
    assert "Analyse mot kjøpsklarhet" in text
    assert "NORAM.OL" in text
    assert "BLOKKERT" in text
