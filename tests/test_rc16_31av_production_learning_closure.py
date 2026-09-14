from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import autonomous_portfolio as ap
import learning_acceptance as la
import market_intelligence as mi
from app_version import APP_VERSION, PREVIOUS_APP_VERSION
from autonomous_decision_reduction import apply_decision_reduction
from market_intelligence import build_main_pdf, build_text_report
from report_export_audit import canonical_public_run, validate_artifacts


def _candidate(index: int) -> dict:
    return {
        "ticker": f"AV{index}.OL",
        "market": "Norge",
        "investment_score": 72.9 - index / 10,
        "risk_score": 30.0,
        "valid_for_decision": True,
        "evidence_valid_for_decision": True,
        "mission_eligible": True,
        "analysis_stage": "EVIDENCE_CONTROLLED",
        "portfolio_action": "REVIEW",
        "portfolio_decision": {"existing_position": False, "blockers": []},
        "decision_readiness": {
            "news": "VERIFIED_FACTS_FOUND", "insider": "CHECKED_NO_EVENTS", "conflicts": 0,
        },
        "raw": {},
    }


def _thirteen_row_run() -> dict:
    rows, reduction = apply_decision_reduction(
        [_candidate(index) for index in range(13)],
        threshold=73.0, near_threshold_gap=6.0, maximum_risk=65.0,
    )
    return canonical_public_run({
        "run_id": "MI-AV-13", "created_at": "2026-08-30T13:29:50+00:00",
        "timezone_name": "Europe/Oslo", "job_id": "MI-REQUIRED-AFTERNOON",
        "job_name": "Obligatorisk ettermiddagsrapport", "trigger": "SCHEDULED",
        "candidates": rows, "summary": {"scanned": 13, "deep_analyzed": 13},
        "report_summary": {"production_buy_threshold": 73.0},
        "autonomous_decision_reduction": reduction,
    })


def test_release_identity_is_av_over_au():
    assert APP_VERSION == "v19.22.0-rc16.31bd"
    assert PREVIOUS_APP_VERSION == "v19.22.0-rc16.31bc"


def test_realistic_thirteen_recommendations_survive_every_export_channel():
    run = _thirteen_row_run()
    text = build_text_report(run).encode("utf-8")
    assert sum(line.startswith("#") for line in text.decode().splitlines()) == 13
    payload = json.dumps(run, ensure_ascii=False, separators=(",", ":"), default=str).encode()
    audit = validate_artifacts(run=run, pdf=build_main_pdf(run), txt=text, json_bytes=payload)
    assert audit["ok"], audit["errors"]


def test_final_release_gate_is_after_parallel_and_controlled_learning():
    source = Path("market_intelligence.py").read_text(encoding="utf-8")
    parallel = source.index('run["parallel_validation"] = save_parallel_validation(parallel)')
    controlled = source.index('run["controlled_discovery_learning"] = run_controlled_discovery_learning')
    gate = source.index('"release_gate": "PENDING"')
    assert parallel < controlled < gate
    assert "validate_report_integrity(run)" in source[gate:]
    assert "validate_artifacts(" in source[gate:]


def test_scheduler_health_rejects_explicit_revalidation_as_last_fixed(monkeypatch):
    job = mi.JobProfile(
        name="Morgen", job_id="MI-REQUIRED-MORNING", schedules=["08:00"],
        weekdays=[0, 1, 2, 3, 4], timezone_name="Europe/Oslo", enabled=True,
        last_run_at="2026-08-30T08:47:09+00:00",
    )
    monkeypatch.setattr(mi, "load_job_history", lambda limit=1000: [{
        "job_id": job.job_id, "type": "Revalidering", "trigger": "REVALIDATION",
        "completed_at": "2026-08-30T08:47:09+00:00",
    }])
    assert mi._latest_scheduled_actual(job) is None


def test_learning_quality_separates_legacy_and_current_cohort():
    portfolio = {"positions": {
        "OLD": {"ticker": "OLD", "learning_cohort": "LEGACY_OBSERVATION", "opened_at": "2026-01-01T00:00:00+00:00"},
        "NEW": {"ticker": "NEW", "learning_cohort": APP_VERSION, "opened_at": "2026-08-30T00:00:00+00:00"},
    }}
    quality = ap.learning_quality_diagnostics(portfolio, [])
    assert quality["active_cohort_open"] == 1
    assert quality["legacy_open"] == 1
    assert quality["strategy_readiness"] == "NOT_VALIDATED"
    assert quality["active_cohort_cap"] == 30
    assert quality["active_cohort_performance"]["open_positions"] == 1
    assert quality["active_cohort_performance"]["benchmark_excess_return_status"] == "PENDING_MARKET_SERIES"


def test_operational_learning_pass_does_not_claim_validated_strategy(monkeypatch):
    monkeypatch.setattr(la, "write_json", lambda *args, **kwargs: None)
    run = {
        "run_id": "AV-LEARNING", "trigger": "TEST", "job_id": "TEST",
        "candidates": [{"ticker": "AAA"}],
        "portfolio_decisions": {"decisions": [{"ticker": "AAA"}]},
        "autonomous_chain": {
            "status": "COMPLETED",
            "learning_decisions": [{"ticker": "AAA", "action": "OBSERVE", "reason": "Følges"}],
            "learning_trades": [],
            "learning_portfolio": {"last_run_id": "AV-LEARNING", "positions": {
                "AAA": {"ticker": "AAA", "learning_cohort": APP_VERSION},
            }, "closed_positions": []},
            "learning_performance": {"return_pct": 0},
        },
    }
    result = la.evaluate_learning_run(run)
    assert result["operational_verdict"] == "PASS"
    assert result["strategy_readiness"] == "NOT_VALIDATED"
    assert result["strategy_quality_gate"]["automatic_production_promotion_allowed"] is False


def test_mobile_delivery_has_durable_open_download_copy_and_return_paths():
    source = Path("mobile_file_delivery.py").read_text(encoding="utf-8")
    assert 'target="_blank"' in source
    assert 'download="{safe_name}"' in source
    assert "st.code(" in source
    assert "Tilbake til programmet" in source
    assert "st.download_button(" in source


def test_learning_horizons_and_caps_are_fail_closed():
    assert ap.LEARNING_OUTCOME_HORIZONS == (1, 5, 20, 60)
    assert ap.LEARNING_ACTIVE_COHORT_MAX_OPEN_POSITIONS == 30
    assert ap.LEARNING_TOTAL_SAFETY_CAP == 120


def test_production_readiness_never_promotes_local_checks_to_live_production():
    from production_readiness import assess_production_readiness

    run = {
        "scan_configuration": {"markets": ["Norge", "Sverige", "USA"]},
        "candidates": [],
        "final_release_gate": {"ok": True},
        "report_integrity": {"ok": True},
        "pdf_delivery": {"validated": True},
        "technical_pdf_delivery": {"validated": True},
    }
    result = assess_production_readiness(run)
    assert result["status"] == "LOCAL_PRODUCTION_CANDIDATE"
    assert result["production_ready"] is False


def test_production_readiness_blocks_unexpected_market_and_moderate_trade():
    from production_readiness import assess_production_readiness

    run = {
        "scan_configuration": {"markets": ["Norge", "Brasil"]},
        "candidates": [{
            "ticker": "BAD", "market": "Brasil",
            "autonomy_outcome_code": "MODERAT_KJØPSANBEFALING",
            "trade_authorized": True,
        }],
        "final_release_gate": {"ok": True},
        "report_integrity": {"ok": True},
        "pdf_delivery": {"validated": True},
        "technical_pdf_delivery": {"validated": True},
    }
    result = assess_production_readiness(run)
    assert result["status"] == "NOT_READY"
    assert result["unexpected_markets"] == ["BRASIL"]
    assert result["moderate_trade_authorizations"] == ["BAD"]
