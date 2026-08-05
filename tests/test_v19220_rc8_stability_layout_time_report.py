from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from app_version import APP_VERSION, PREVIOUS_APP_VERSION, RANKING_MODEL_VERSION, AUTONOMY_POLICY_VERSION
from decision_report import build_decision_report, candidate_source_consensus
from local_time import AUTO_TIMEZONE, display_time, display_timezone_name
from ui_layout_contracts import currency_status_html, data_freshness_label, format_decimal, special_banner_enabled

ROOT = Path(__file__).resolve().parents[1]


def test_rc8_version_and_protected_engine_versions_are_unchanged():
    assert APP_VERSION == "v19.22.0-rc13"
    assert PREVIOUS_APP_VERSION == "v19.22.0-rc12"
    assert RANKING_MODEL_VERSION == "v19.16.0"
    assert AUTONOMY_POLICY_VERSION == "v19.16.0"


def test_currency_format_is_two_decimals_and_mobile_css_is_one_column():
    assert format_decimal(1.8661999702453613) == "1,87"
    html = currency_status_html([("Siste kurs", format_decimal(1.8661999702453613), "Ferske data")])
    assert "grid-template-columns:1fr" in html
    assert "1,87" in html
    assert "1,866199" not in html


def test_special_banner_widget_state_wins_immediately():
    assert special_banner_enabled({"special_watch_banner_enabled_v18615": True}, {"special_watch_enabled_v18619": False}) is False
    assert special_banner_enabled({"special_watch_banner_enabled_v18615": False}, {"special_watch_enabled_v18619": True}) is True


def test_display_timezone_is_presentation_only_and_supports_travel_zones():
    assert display_timezone_name({"display_timezone": "Europe/Lisbon"}) == "Europe/Lisbon"
    assert display_timezone_name({"display_timezone": "America/Sao_Paulo"}) == "America/Sao_Paulo"
    assert display_timezone_name({"display_timezone": AUTO_TIMEZONE}, browser_tz="Europe/Lisbon") == "Europe/Lisbon"
    text = display_time("2026-08-04T16:00:20+00:00", "Europe/Oslo")
    assert "18:00:20" in text and "Europe/Oslo" in text


def test_data_freshness_marks_old_data():
    now = datetime(2026, 8, 4, 18, 0, tzinfo=timezone.utc)
    assert data_freshness_label("2026-08-04T17:55:00+00:00", now=now)[1] == "fresh"
    assert data_freshness_label("2026-08-04T12:00:00+00:00", now=now)[1] == "stale"


def test_independent_source_count_prefers_claim_ledger_original_publishers():
    candidate = {
        "source_consensus": {"independent_sources": 3},
        "analysis_transparency": {"claim_ledger": {"independent_source_count": 1, "verified_claim_count": 2}},
    }
    result = candidate_source_consensus(candidate)
    assert result["independent_sources"] == 1
    assert result["source_count_basis"] == "original_publisher_verified_claims"
    assert result["source_count_consistent"] is True


def test_decision_report_exposes_separate_quality_dimensions_and_hides_legacy_score():
    run = {
        "run_id": "TEST-RC8",
        "created_at": "2026-08-04T16:00:00+00:00",
        "timezone_name": "Europe/Oslo",
        "markets": ["Danmark"],
        "data_quality": {"score": 100},
        "combined_data_quality": {"evaluated": 1, "overall_valid": 1},
        "candidates": [{
            "ticker": "TEST.CO", "investment_score": 70.0, "final_score": 70.0,
            "portfolio_action": "REVIEW", "decision_readiness": {"insider": "CHECKED_NO_EVENTS"},
            "confidence": {"documentation_coverage": 90, "market_data_coverage": 100, "source_confidence": 50, "decision_confidence": 65},
            "analysis_transparency": {"claim_ledger": {"independent_source_count": 1, "verified_claim_count": 1}},
        }],
    }
    report = build_decision_report(run, None, {"type": "UTKAST", "label": "Utkast"})
    quality = report["quality_dimensions"]
    assert quality["candidate_evidence_coverage"] == 100.0
    assert quality["candidate_evidence_ready_count"] == 1
    assert report["reliability"]["deprecated"] is True
    assert report["reliability"]["display"] is False


def test_scheduler_times_remain_locked_to_oslo_contract():
    source = (ROOT / "market_intelligence.py").read_text(encoding="utf-8")
    assert '"08:00"' in source and '"22:00"' in source
    assert "Europe/Oslo" in source


def test_rc8_pdf_source_uses_clear_labels_and_material_change_threshold():
    source = (ROOT / "market_intelligence.py").read_text(encoding="utf-8")
    assert "Kandidatenes evidens" in source
    assert "Uavhengige kilder" in source
    assert "Beslutningsstyrke rapport" in source
    assert "Vesentlige scoreendringer (>= 1,00)" in source
    assert "Ingen vesentlige scoreendringer" in source
    assert "CondPageBreak(84*mm)" in source


def test_runtime_reset_does_not_include_auth_or_persistent_settings():
    source = (ROOT / "app.py").read_text(encoding="utf-8")
    reset_block = source[source.index("_TRANSIENT_UI_EXACT_KEYS_V19220_RC8"):source.index("def _render_display_time_settings_v19220_rc8")]
    assert "authenticated" not in reset_block
    assert "remember" not in reset_block.lower()
    assert "save_settings" not in reset_block
