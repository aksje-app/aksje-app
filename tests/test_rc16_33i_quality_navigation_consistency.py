from __future__ import annotations

from pathlib import Path

from quality_valuation import _apply_grade, ensure_valuation_context, evaluate_company


def _base_row():
    return {
        "ticker": "AFG.OL",
        "name": "AF Gruppen ASA",
        "country": "Norway",
        "currency": "NOK",
        "sector": "Industrials",
        "industry": "Engineering & Construction",
        "price": 197.20,
        "trailing_eps": 11.0,
        "forward_eps": 12.7,
        "annual_eps": [9.93, 6.52, 3.72, 7.74],
        "financial_date": "2025-12-31",
        "fiscal_periods": ["2025-12-31", "2024-12-31", "2023-12-31", "2022-12-31"],
        "roce": .2817,
        "roce_history": [.2817, .2382, .17, .15],
        "free_cash_flow": 2_120_000_000,
        "free_cash_flow_history": [2_120_000_000, 1_960_000_000, 1_020_000_000, 1_500_000_000],
        "operating_margin_history": [.045, .033, .021, .028],
        "debt_history": [1_510_000_000, 1_310_000_000, 1_340_000_000],
    }


def test_legacy_scenario_context_is_backfilled():
    row = {
        "price": 197.20,
        "fair_price_scenario": 193.04,
        "entry_range_scenario": [164.08, 193.04],
    }
    out = ensure_valuation_context(row)
    assert out["price_vs_scenario_pct"] == 2.2
    assert out["valuation_position"] == "NEAR_SCENARIO"
    assert "2.2%" in out["valuation_position_text"]


def test_five_stars_cannot_coexist_with_subscore_below_four():
    item = {
        "sector_policy": "STANDARD",
        "quality_state": "QUALITY",
        "roce_pct": 30,
        "roce_trend": "FORBEDRENDE",
        "price": 100,
        "fair_price_scenario": 100,
        "normalized_pe": 10,
        "reported_pe": 10,
        "financial_age_days": 100,
        "annual_eps_history": [1, 1, 1, 1],
        "roce_history_pct": [30, 28, 26, 24],
        "evidence_ready": True,
        "provider_partial": False,
    }
    _apply_grade(item)
    assert item["valuation_score"] == 3
    assert item["overall_stars"] <= 4


def test_quality_confirmed_does_not_report_quality_weak_reason():
    row = evaluate_company(_base_row())
    if row["quality_state"] in {"QUALITY", "IMPROVING"}:
        assert row["review_reason_category"] == "QUALITY_CONFIRMED"


def test_overview_legacy_disagreement_state_never_claims_zero_zero_complete():
    src = Path("pages/overview.py").read_text(encoding="utf-8")
    assert "IKKE KLASSIFISERT ENNÅ" in src
    assert "Ny kvalitetskjøring kreves" in src
    assert "classification_available" in src
    assert "disagreements == v2_weaker + v2_stronger" in src
    assert 'weaker_class = "tone-danger" if v2_weaker > 0 else "tone-neutral"' in src
    assert 'stronger_class = "tone-success" if v2_stronger > 0 else "tone-neutral"' in src


def test_diagnosis_and_zip_stay_in_app_until_explicit_download():
    src = Path("public_report_ui.py").read_text(encoding="utf-8")
    assert "def _render_in_app_file" in src
    assert "Du blir på denne siden til du selv velger å laste ned filen." in src
    assert "Diagnosen kan leses og kopieres her" in src
    assert "st.download_button" in src
    assert "_return_to_report_choices" in src
    file_branch = src.split('file_token = str(st.query_params.get("public_file_token")', 1)[1]
    assert "_render_in_app_file(st, artifact, return_to=return_to)" in file_branch


def test_mobile_bottom_nav_forces_one_horizontal_row():
    src = Path("ui_library/theme.py").read_text(encoding="utf-8")
    assert "flex-direction:row!important" in src
    assert "flex-wrap:nowrap!important" in src
    assert "flex:1 1 0!important" in src


def test_old_report_rows_recompute_scenario_distance_in_ui_and_pdfs():
    ui = Path("quality_valuation_ui.py").read_text(encoding="utf-8")
    full = Path("quality_extended_report.py").read_text(encoding="utf-8")
    assert "ensure_valuation_context(dict(item))" in ui
    assert "ensure_valuation_context(dict(item))" in full
