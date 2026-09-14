from __future__ import annotations

import io
import zipfile
from pathlib import Path

import autonomous_portfolio as ap
import manual_job_background as mb
import market_intelligence as mi
from app_version import APP_VERSION, PREVIOUS_APP_VERSION


ROOT = Path(__file__).resolve().parents[1]


def _zip_bytes() -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("status.json", "{}")
    return buffer.getvalue()


def test_release_identity_and_mobile_safe_diagnostic_delivery(tmp_path, monkeypatch):
    assert APP_VERSION == "v19.22.0-rc16.31bd"
    assert PREVIOUS_APP_VERSION == "v19.22.0-rc16.31bc"
    monkeypatch.setattr(mb, "__file__", str(tmp_path / "manual_job_background.py"))
    first = mb.publish_diagnostic_download(_zip_bytes(), "Diagnose æøå.zip")
    second = mb.publish_diagnostic_download(_zip_bytes(), "Diagnose æøå.zip")
    assert first == second
    assert first["url"].startswith("/app/static/diagnostics/")
    assert (tmp_path / "static" / "diagnostics" / first["public_name"]).read_bytes().startswith(b"PK")
    report_source = (ROOT / "market_intelligence.py").read_text(encoding="utf-8")
    overview_source = (ROOT / "autonomy_overview.py").read_text(encoding="utf-8")
    delivery_source = (ROOT / "mobile_file_delivery.py").read_text(encoding="utf-8")
    assert "render_mobile_file_delivery(" in report_source
    assert "render_mobile_file_delivery(" in overview_source
    assert 'target="_blank" rel="noopener noreferrer"' in delivery_source
    assert "st.code(" in delivery_source


def test_delivery_retry_excludes_test_and_revalidation_rows(monkeypatch):
    jobs, _ = mi.ensure_required_report_jobs([])
    job = jobs[0]
    monkeypatch.setattr(mi, "load_jobs", lambda: jobs)
    monkeypatch.setattr(mi, "load_job_history", lambda limit=500: [
        {"job_id": job.job_id, "run_id": "REVALIDATED", "type": "Revalidering", "trigger": "REVALIDATION"},
        {"job_id": job.job_id, "run_id": "TEST", "type": "Test", "trigger": "SCHEDULED_REPORT_TEST_NOTIFICATION"},
    ])
    monkeypatch.setattr(mi, "load_run", lambda run_id: (_ for _ in ()).throw(AssertionError(run_id)))
    assert mi.retry_pending_required_report_deliveries()["attempted"] == []


def test_pdf_language_and_capacity_contracts_are_closed():
    source = (ROOT / "market_intelligence.py").read_text(encoding="utf-8")
    decision = (ROOT / "decision_report.py").read_text(encoding="utf-8")
    language = (ROOT / "norwegian_report_language.py").read_text(encoding="utf-8")
    portfolio = (ROOT / "report_portfolio_intelligence.py").read_text(encoding="utf-8")
    assert "strengt kjøpsgodkjent" in decision
    assert "moderat kjøpsanbefalt" in decision
    assert "available_position_slots" in decision and "available_position_slots" in portfolio
    assert "Likviditeten er under minimumskravet" in language
    assert "er merket streng eller moderat kjøpsanbefaling er anbefalinger" in source


def test_legacy_sell_entry_context_is_backfilled_without_mutating_raw_rows():
    raw = [
        {"trade_id": "S1", "timestamp": "2026-08-02T00:00:00+00:00", "action": "SELL", "ticker": "ABC", "pnl": -5},
        {"trade_id": "B1", "timestamp": "2026-08-01T00:00:00+00:00", "action": "BUY", "ticker": "ABC", "entry_score": 70, "entry_risk_score": 40, "evidence_valid_at_entry": True},
    ]
    result = ap._backfill_learning_trade_context(raw)
    sell = next(row for row in result if row["action"] == "SELL")
    assert sell["entry_score"] == 70
    assert sell["entry_risk_score"] == 40
    assert sell["source_buy_trade_id"] == "B1"
    assert "entry_score" not in raw[0]


def test_learning_quality_tiers_cap_and_stop_slippage(monkeypatch):
    strong = {"ticker": "ABC", "market": "USA", "valid_for_decision": True, "evidence_valid_for_decision": True,
              "autonomy_adjusted_investment_score": 70, "risk_score": 40}
    weak = {**strong, "ticker": "XYZ", "evidence_valid_for_decision": False}
    assert ap._learning_tier(strong) == "VALIDATION"
    assert ap._learning_tier(weak) == "EXPLORATION"
    assert ap._learning_benchmark(strong) == ("USA", "^GSPC")
    assert ap.LEARNING_MAX_OPEN_POSITIONS == 60

    portfolio = {"positions": {"ABC": {"ticker": "ABC", "quantity": 1, "average_price": 100,
        "strategy": "Growth", "entry_score": 70, "opened_at": "2026-08-01T00:00:00+00:00"}},
        "closed_positions": [], "realized_pnl": 0}
    monkeypatch.setattr(ap, "_record_learning_trade", lambda row: None)
    trade = ap._close_learning_position(portfolio, "ABC", 90, "Læringsobservasjon: stop loss", "RUN")
    assert trade["configured_trigger_pct"] == -5.0
    assert trade["trigger_slippage_pct"] == -5.0
    assert trade["gap_or_delayed_exit"] is True


def test_quality_diagnostics_exposes_mixed_cohorts_and_denominator():
    portfolio = {"positions": {"ABC": {"ticker": "ABC", "quantity": 1, "average_price": 100,
        "last_price": 105, "evidence_valid_at_entry": False, "freshness_status": "STALE_NOT_IN_CANDIDATE_SET",
        "opened_at": "2026-01-01T00:00:00+00:00", "benchmark_ticker": "^GSPC"}},
        "closed_positions": [], "realized_pnl": 0, "total_entry_notional": 100}
    trades = [
        {"action": "SELL", "ticker": "OLD", "pnl": -10, "strategy_impl_version": "legacy", "reason": "stop loss", "gap_or_delayed_exit": True},
        {"action": "BUY", "ticker": "ABC", "learning_cohort": APP_VERSION},
    ]
    quality = ap.learning_quality_diagnostics(portfolio, trades)
    perf = ap.learning_portfolio_performance(portfolio)
    assert quality["stale_open"] == 1
    assert quality["gap_or_delayed_stop_exits"] == 1
    assert len(quality["cohorts"]) == 2
    assert perf["return_denominator"] == "CUMULATIVE_ENTRY_NOTIONAL"
    assert perf["mature_observations_20d"] == 1
