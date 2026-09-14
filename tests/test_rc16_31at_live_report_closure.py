from __future__ import annotations

from datetime import datetime, timedelta, timezone
import io
import json
from pathlib import Path
import sys
from types import SimpleNamespace
from zipfile import ZipFile

import controlled_parameter_learning as learning
import manual_job_background as background
import market_intelligence as market_reports
import paper_scanner_runtime as scanner_runtime
from norwegian_report_language import label_for
from report_channel_consistency import build_channel_projection
from report_portfolio_intelligence import build_candidate_watch_queue


def test_scanner_configuration_defaults_to_standard_service_capacity(monkeypatch):
    monkeypatch.delenv("SCANNER_MEMORY_SOFT_LIMIT_MB", raising=False)
    config = scanner_runtime.scanner_configuration_snapshot()
    assert config["scanner_memory_soft_limit_mb"] == 1700.0
    assert config["scanner_min_tickers_per_cycle"] == 1
    assert config["automated_markets"] == ["USA", "NORGE", "SVERIGE"]


def test_channel_projection_carries_exact_public_quality_denominators():
    document = {
        "metadata": {"report_id": "MI-AT", "run_id": "MI-AT"},
        "sections": [
            {"key": "decision_overview", "payload": {"candidate_count": 63}},
            {"key": "quality_dimensions", "payload": {
                "market_data_quality": 90,
                "candidate_evidence_ready_count": 40,
                "candidate_count": 63,
            }},
            {"key": "candidate_decisions", "payload": []},
        ],
    }
    quality = build_channel_projection(document)["quality"]
    assert quality == {
        "market_data_label": "Beslutningsjustert markedsdata",
        "market_data_score": 90,
        "evidence_label": "Evidensklar etter kontroll",
        "evidence_ready": 40,
        "evidence_controlled": 0,
        "evidence_success_rate": 0.0,
        "evidence_not_prioritized": 0,
        "candidate_total": 63,
    }


def test_moderate_recommendations_are_not_duplicated_in_watch_queue():
    rows = [
        {"ticker": "GOOGL", "market": "USA", "investment_score": 72.1,
         "analytical_recommendation_ready": True, "portfolio_decision": {"blocker_codes": ["SCORE_BELOW_THRESHOLD"]}},
        {"ticker": "AMGN", "market": "USA", "investment_score": 72.7,
         "analytical_recommendation_ready": False, "portfolio_decision": {"blocker_codes": ["SCORE_BELOW_THRESHOLD"]}},
    ]
    assert [row["ticker"] for row in build_candidate_watch_queue(rows)] == ["AMGN"]


def test_investor_blocker_codes_have_plain_norwegian_labels():
    assert label_for("MISSION_INELIGIBLE") == "Utenfor investeringsoppdraget"
    assert label_for("MAX_OPEN_POSITIONS") == "Ingen ledig posisjonsplass"
    assert label_for("EVIDENCE_NOT_READY") == "Evidensgrunnlaget er ikke beslutningsklart"


def test_identical_risk_proposal_is_silent_for_seven_days():
    now = datetime(2026, 8, 28, 12, 0, tzinfo=timezone.utc)
    state = {
        "last_risk_proposal_fingerprint": "same",
        "last_risk_proposal_notification_at": (now - timedelta(hours=6)).isoformat(),
    }
    assert learning.risk_proposal_notification_due(state, "same", now=now) is False
    assert learning.risk_proposal_notification_due(state, "changed", now=now) is True
    state["last_risk_proposal_notification_at"] = (now - timedelta(days=8)).isoformat()
    assert learning.risk_proposal_notification_due(state, "same", now=now) is True


def test_render_cron_checks_due_reports_every_five_minutes():
    assert 'schedule: "*/5 * * * *"' in Path("render.yaml").read_text(encoding="utf-8")


def test_diagnostic_prefers_persisted_scanner_runtime_over_web_fallback(monkeypatch):
    monkeypatch.setenv("SCANNER_MEMORY_SOFT_LIMIT_MB", "410")
    monkeypatch.setattr(background, "get_status", lambda *_: {
        "execution_id": "MBJ-OLD", "state": "COMPLETED",
        "completed_at": "2026-08-25T18:36:27+00:00",
    })
    monkeypatch.setattr(scanner_runtime, "load_scanner_status", lambda: {
        "execution_id": "PAPER-CURRENT", "state": "SKIPPED_POLICY",
        "scanner_configuration": {
            "automated_markets": ["USA", "NORGE", "SVERIGE"],
            "scanner_max_tickers": 30,
            "scanner_memory_soft_limit_mb": 1700.0,
            "scanner_min_tickers_per_cycle": 1,
            "source": "paper_scanner_runtime",
            "secret_values_included": False,
        },
    })
    monkeypatch.setattr(scanner_runtime, "load_scanner_checkpoint", lambda: {})
    monkeypatch.setitem(sys.modules, "learning_acceptance", SimpleNamespace(build_learning_diagnostics=lambda: {"acceptance": {}}))
    monkeypatch.setitem(sys.modules, "report_test_mode", SimpleNamespace(load_report_test_mode=lambda: {}))
    monkeypatch.setitem(sys.modules, "report_system_check", SimpleNamespace(load_report_system_check=lambda: {}))
    monkeypatch.setitem(sys.modules, "notifier", SimpleNamespace(pushover_audit=lambda limit=50: []))
    monkeypatch.setitem(sys.modules, "scheduled_runner", SimpleNamespace(load_unattended_state=lambda: {}))
    monkeypatch.setitem(sys.modules, "execution_coordination", SimpleNamespace(report_execution_owner=lambda: {}))
    monkeypatch.setitem(sys.modules, "runtime_identity", SimpleNamespace(runtime_identity_snapshot=lambda: {}))
    monkeypatch.setitem(sys.modules, "runtime_memory", SimpleNamespace(memory_snapshot=lambda: {}))

    payload, filename = background.diagnostic_bundle("MBJ-OLD")
    with ZipFile(io.BytesIO(payload)) as archive:
        configuration = json.loads(archive.read("scanner/SCANNER_CONFIGURATION.json"))
        context = json.loads(archive.read("runtime/DIAGNOSTIC_CONTEXT.json"))
    assert configuration["scanner_memory_soft_limit_mb"] == 1700.0
    assert configuration["collector_process_soft_limit_mb"] == 410.0
    assert configuration["source"] == "persisted_paper_scanner_runtime"
    assert context["selected_status_is_historical"] is True
    assert filename.startswith("Bakgrunnsjobb_diagnose_")
    assert filename.endswith("_MBJ-OLD.zip")


def test_pushover_uses_same_quality_projection_as_pdf_and_json(monkeypatch):
    captured = {}
    monkeypatch.setattr(market_reports, "_read", lambda *args, **kwargs: {})
    monkeypatch.setattr(market_reports, "_write", lambda *args, **kwargs: None)
    monkeypatch.setattr(market_reports, "_audit", lambda *args, **kwargs: None)
    monkeypatch.setitem(sys.modules, "notifier", SimpleNamespace(
        send_pushover_alert=lambda message, title="", **kwargs: (
            captured.update(message=message, title=title) or True, None
        ),
    ))
    run = {
        "run_id": "MI-AT-CHANNEL", "report_id": "MI-AT-CHANNEL",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "timezone_name": "Europe/Oslo", "trigger": "SCHEDULED",
        "scheduled_for": datetime.now(timezone.utc).isoformat(),
        "markets": ["Norge", "Sverige", "USA"], "changes": {},
        "report_status": {"label": "ENDELIG"},
        "report_revision": {"revision_label": "R1"},
        "report_summary": {
            "coverage_candidate_total": 63, "deep_analyzed": 63,
            "evidence_data_ready": 40, "analytical_buy_recommendations": 13,
            "buy_candidates": 0, "moderate_buy_recommendations": 13,
        },
        "report_document": {
            "metadata": {"report_id": "MI-AT-CHANNEL", "run_id": "MI-AT-CHANNEL", "report_label": "Ettermiddagsrapport"},
            "sections": [
                {"key": "decision_overview", "payload": {"candidate_count": 63}},
                {"key": "quality_dimensions", "payload": {
                    "market_data_quality": 90,
                    "candidate_evidence_ready_count": 40,
                    "candidate_count": 63,
                }},
                {"key": "candidate_decisions", "payload": []},
            ],
        },
    }
    job = market_reports.JobProfile(
        job_id="MI-REQUIRED-AFTERNOON", name="Obligatorisk ettermiddagsrapport",
        notification_mode="ALWAYS", include_top3_in_notification=False,
    )
    ok, _detail = market_reports._notification(job, run)
    assert ok is True
    assert "Analysert: 63" in captured["message"]
    assert "markedsdata (beslutningsjustert) 90/100" in captured["message"]
    assert "evidens 40/63" in captured["message"]
