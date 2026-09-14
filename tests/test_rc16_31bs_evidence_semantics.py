from pathlib import Path

import app_version
from decision_report import build_decision_report
from report_channel_consistency import build_channel_projection


def _document_from_quality(quality):
    return {
        "metadata": {"report_id": "MI-BS", "run_id": "MI-BS"},
        "sections": [
            {"key": "decision_overview", "payload": {"candidate_count": 73}},
            {"key": "quality_dimensions", "payload": quality},
            {"key": "candidate_decisions", "payload": []},
        ],
    }


def test_version_is_bs():
    assert app_version.APP_VERSION == "v19.22.0-rc16.31bs"


def test_evidence_success_rate_uses_controlled_population_not_all_candidates():
    run = {
        "run_id": "MI-BS",
        "candidates": [],
        "report_summary": {"coverage_candidate_total": 73},
        "combined_data_quality": {"evaluated": 73, "overall_valid": 13},
        "analysis_stages": {"stage3_evidence_controlled": 20},
        "universe_coverage": [],
    }
    report = build_decision_report(run, None, {"type": "MANUELL_RAPPORT", "label": "Test"})
    quality = report["quality_dimensions"]
    assert quality["candidate_count"] == 73
    assert quality["candidate_evidence_ready_count"] == 13
    assert quality["candidate_evidence_controlled_count"] == 20
    assert quality["candidate_evidence_success_rate"] == 65.0
    assert quality["candidate_evidence_not_prioritized_count"] == 53
    # Kept only for backward-compatible JSON consumers, not as the report-facing score.
    assert quality["candidate_evidence_coverage"] == 17.8


def test_ready_count_is_never_larger_than_controlled_denominator():
    run = {
        "run_id": "MI-BS2",
        "candidates": [],
        "report_summary": {"coverage_candidate_total": 20},
        "combined_data_quality": {"evaluated": 20, "overall_valid": 7},
        "analysis_stages": {},
        "universe_coverage": [],
    }
    quality = build_decision_report(run, None, {"type": "MANUELL_RAPPORT"})["quality_dimensions"]
    assert quality["candidate_evidence_controlled_count"] == 7
    assert quality["candidate_evidence_success_rate"] == 100.0
    assert quality["candidate_evidence_not_prioritized_count"] == 13


def test_public_channel_projection_exposes_all_three_evidence_counts():
    quality = {
        "market_data_quality": 90,
        "candidate_evidence_ready_count": 13,
        "candidate_evidence_controlled_count": 20,
        "candidate_evidence_success_rate": 65.0,
        "candidate_evidence_not_prioritized_count": 53,
        "candidate_count": 73,
    }
    public = build_channel_projection(_document_from_quality(quality))["quality"]
    assert public["evidence_ready"] == 13
    assert public["evidence_controlled"] == 20
    assert public["evidence_success_rate"] == 65.0
    assert public["evidence_not_prioritized"] == 53
    assert public["candidate_total"] == 73


def test_pdf_source_labels_metric_as_ready_after_control_and_explains_not_prioritized():
    source = Path("market_intelligence.py").read_text(encoding="utf-8")
    assert "Evidensklar etter kontroll" in source
    assert "kandidater ble prioritert til full evidenskontroll" in source
    assert "kandidater ble ikke prioritert til full evidenskontroll" in source
    assert "quality_status(evidence_success_rate)" in source
