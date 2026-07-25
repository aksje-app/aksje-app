from __future__ import annotations

from io import BytesIO

import pytest
from pypdf import PdfReader

from app_version import (
    APP_VERSION,
    AUTONOMY_POLICY_VERSION,
    DATABASE_SCHEMA_VERSION,
    RANKING_MODEL_VERSION,
    REPORT_SCHEMA_VERSION,
    SOURCE_CLASSIFIER_VERSION,
    get_version_contract,
    validate_version_contract,
)
import market_intelligence as mi
from report_contracts import (
    ReportContractError,
    build_report_document,
    build_report_identity,
    ensure_report_document,
    section_payload,
    validate_report_document,
)


def _run(created_at: str = "2026-07-25T18:30:00+00:00") -> dict:
    return {
        "run_id": "MI-1920-CONTRACT",
        "created_at": created_at,
        "timezone_name": "Europe/Oslo",
        "job_id": "JOB-1920",
        "job_name": "Kontrakttest",
        "trigger": "SCHEDULED",
        "markets": ["Norge", "USA"],
        "summary": {"scanned": 2, "deep_analyzed": 2, "proposals": 1, "recommended": 1},
        "data_quality": {"score": 91, "label": "UTMERKET"},
        "candidates": [
            {
                "rank": 1,
                "ticker": "EQNR.OL",
                "market": "Norge",
                "investment_score": 82.5,
                "portfolio_action": "REVIEW",
                "status": "ANBEFALT FOR VURDERING",
                "valid_for_decision": True,
                "evidence_valid_for_decision": True,
            }
        ],
        "changes": {"new": ["EQNR.OL"], "improved": [], "weakened": [], "dropped": []},
        "report_status": {"state": "FINAL", "label": "ENDELIG"},
        "report_revision": {"revision": 1, "revision_label": "R1", "content_sha256": "abc"},
    }


def test_version_contract_separates_app_and_compatibility_versions():
    contract = get_version_contract(component_name="market_intelligence", component_version="engine-1")
    assert APP_VERSION == "v19.3.0"
    assert contract["app_version"] == APP_VERSION
    assert contract["report_schema_version"] == REPORT_SCHEMA_VERSION
    assert contract["database_schema_version"] == DATABASE_SCHEMA_VERSION
    assert contract["ranking_model_version"] == RANKING_MODEL_VERSION
    assert contract["autonomy_policy_version"] == AUTONOMY_POLICY_VERSION
    assert contract["source_classifier_version"] == SOURCE_CLASSIFIER_VERSION
    assert contract["component_version"] == "engine-1"
    assert validate_version_contract(contract)["ok"] is True


def test_all_scheduled_periods_have_one_allowed_mission():
    cases = {
        "2026-07-25T05:00:00+00:00": ("MORGENRAPPORT", "PREPARE_TRADING_DAY"),
        "2026-07-25T11:00:00+00:00": ("DAGSRAPPORT", "MONITOR_INTRADAY"),
        "2026-07-25T16:00:00+00:00": ("KVELDSRAPPORT", "REVIEW_TRADING_DAY"),
        "2026-07-25T23:00:00+00:00": ("NATTRAPPORT", "MONITOR_OVERNIGHT_RISK"),
    }
    for created_at, expected in cases.items():
        identity = build_report_identity("SCHEDULED", created_at=created_at, timezone_name="Europe/Oslo")
        assert (identity["type"], identity["mission_code"]) == expected


def test_explicit_type_mission_conflict_fails_closed():
    run = _run()
    run["report_identity"] = {
        "type": "KVELDSRAPPORT",
        "label": "Kveldsrapport",
        "slug": "Kveldsrapport",
        "mission_code": "PREPARE_TRADING_DAY",
    }
    with pytest.raises(ReportContractError):
        build_report_document(run)


def test_legacy_identity_is_upgraded_without_changing_candidate_results():
    run = _run()
    run["report_identity"] = {"type": "KVELDSRAPPORT", "label": "Kveldsrapport", "slug": "Kveldsrapport"}
    original_candidate = dict(run["candidates"][0])
    document = ensure_report_document(run)
    assert validate_report_document(document)["ok"] is True
    assert document["metadata"]["mission_code"] == "REVIEW_TRADING_DAY"
    assert document["metadata"]["app_version"] == APP_VERSION
    assert run["candidates"][0] == original_candidate
    assert run["report_contract_validation"]["ok"] is True


def test_report_document_is_shared_by_text_pdf_and_archive():
    run = _run()
    document = ensure_report_document(run)
    candidates = section_payload(document, "candidate_decisions", [])
    assert candidates[0]["ticker"] == "EQNR.OL"

    text = mi.build_text_report(run)
    assert "Oppdrag: Oppsummer dagen og forbered neste handelsdag" in text
    assert f"Appversjon: {APP_VERSION}" in text
    assert f"Rapportskjema: {REPORT_SCHEMA_VERSION}" in text

    pdf_text = "\n".join(page.extract_text() or "" for page in PdfReader(BytesIO(mi.build_pdf(run))).pages)
    assert APP_VERSION in pdf_text
    assert REPORT_SCHEMA_VERSION in pdf_text
    assert "Oppsummer dagen og forbered neste handelsdag" in pdf_text

    archived = mi._archive_entry(run)
    assert archived["app_version"] == APP_VERSION
    assert archived["report_schema_version"] == REPORT_SCHEMA_VERSION
    assert archived["mission_code"] == "REVIEW_TRADING_DAY"


def test_document_has_required_renderer_independent_sections():
    document = build_report_document(_run())
    keys = [row["key"] for row in document["sections"]]
    assert keys == [
        "executive_summary",
        "decision_overview",
        "candidate_decisions",
        "changes",
        "decision_diffs",
        "counter_hypotheses",
        "next_run_tasks",
        "historical_evaluations",
        "events",
        "confidence_profile",
        "report_reliability",
        "source_consensus",
        "controlled_learning_guard",
        "technical_status",
    ]
    assert document["contract"] == "AI_AKSJE_ANALYZER_REPORT_DOCUMENT"
    assert document["schema_version"] == REPORT_SCHEMA_VERSION
