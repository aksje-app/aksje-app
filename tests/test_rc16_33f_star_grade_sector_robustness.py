from __future__ import annotations

from datetime import datetime, timezone
from io import BytesIO

from pypdf import PdfReader

from quality_valuation import add_peer_context, evaluate_company
from quality_valuation_ui import build_screen_pdf
from quality_extended_report import build_extended_analysis_pdf


NOW = datetime(2026, 9, 26, tzinfo=timezone.utc)


def base(**changes):
    row = {
        "ticker": "TEST.OL",
        "name": "Test ASA",
        "country": "Norway",
        "currency": "NOK",
        "sector": "Industrials",
        "industry": "Engineering & Construction",
        "price": 100,
        "trailing_eps": 8,
        "forward_eps": 9,
        "annual_eps": [8, 7, 6, 5],
        "financial_date": "2025-12-31",
        "fiscal_periods": ["2025-12-31", "2024-12-31", "2023-12-31", "2022-12-31"],
        "roce": .18,
        "roce_history": [.18, .17, .16, .15],
        "free_cash_flow": 100,
        "free_cash_flow_history": [100, 90, 80, 70],
        "operating_margin_history": [.15, .14, .13, .12],
        "debt_history": [200, 210, 220, 230],
    }
    row.update(changes)
    return row


def test_star_grade_is_explainable_and_all_indicators_are_colored():
    row = evaluate_company(base(), as_of=NOW)
    assert 1 <= row["overall_stars"] <= 5
    assert row["overall_grade_color"].startswith("#")
    for key in ("quality", "valuation", "trend", "data"):
        assert 1 <= row[f"{key}_score"] <= 5
        assert row[f"{key}_color"].startswith("#")
    assert row["why_now"].startswith("Hvorfor nå:")
    assert row["next_star_requirement"]
    assert "35%" in row["grade_method"]


def test_financial_insurance_uses_roe_and_caps_grade_without_underwriting_or_solvency():
    row = evaluate_company(base(
        ticker="PROT.OL",
        name="Protector-like Insurance",
        sector="Financial Services",
        industry="Insurance - Property & Casualty",
        is_financial=True,
        roce=None,
        roce_history=[],
        roe_history=[.36, .33, .30, .28],
        free_cash_flow=None,
        free_cash_flow_history=[],
    ), as_of=NOW)
    assert row["sector_policy"] == "FINANCIAL"
    assert row["sector_subtype"] == "INSURANCE"
    assert row["roe_pct"] is not None
    assert row["overall_stars"] <= 4
    assert row["sector_specific_evidence"] is False
    assert any("combined ratio/solvens" in warning for warning in row["warnings"])
    assert not any("ROCE/ROACE" in warning for warning in row["warnings"])


def test_bank_capital_evidence_is_recognized_without_reinterpreting_roce():
    row = evaluate_company(base(
        ticker="BANK.OL",
        name="Bank ASA",
        sector="Financial Services",
        industry="Banks - Regional",
        is_financial=True,
        roce=None,
        roce_history=[],
        roe_history=[.17, .16, .15, .14],
        cet1_ratio=.18,
    ), as_of=NOW)
    assert row["sector_policy"] == "FINANCIAL"
    assert row["sector_subtype"] == "BANK"
    assert row["sector_specific_evidence"] is True
    assert not any("CET1/kapitaldekning" in warning for warning in row["warnings"])


def test_real_estate_fails_closed_without_ffo_affo_nav():
    row = evaluate_company(base(
        ticker="PROP.OL",
        sector="Real Estate",
        industry="Real Estate Services",
        roce=None,
        roce_history=[],
    ), assumed_pe=15, as_of=NOW)
    assert row["sector_policy"] == "REAL_ESTATE"
    assert row["quality_state"] == "SECTOR_METRIC_REQUIRED"
    assert row["overall_stars"] <= 2
    assert row["entry_range_scenario"] is None


def test_shipping_is_cyclical_and_peer_pe_does_not_create_false_cheap_signal():
    rows = [
        evaluate_company(base(
            ticker=f"SHIP{i}.OL",
            sector="Industrials",
            industry="Marine Shipping",
            roce=.11,
            roce_history=[.11, .10, .09, .08],
        ), as_of=NOW)
        for i in range(4)
    ]
    add_peer_context(rows)
    assert all(row["sector_policy"] == "CYCLICAL" for row in rows)
    assert all(row.get("entry_range_scenario") is None for row in rows)
    assert all(row["overall_stars"] <= 4 for row in rows)


def test_capital_intensive_company_is_not_forced_through_standard_12pct_roce_gate():
    row = evaluate_company(base(
        ticker="UTIL.ST",
        country="Sweden",
        currency="SEK",
        sector="Utilities",
        industry="Regulated Electric",
        roce=.09,
        roce_history=[.09, .085, .08, .075],
        free_cash_flow=50,
        free_cash_flow_history=[50, 40, 30, 20],
    ), as_of=NOW)
    assert row["sector_policy"] == "CAPITAL_INTENSIVE"
    assert row["quality_evidence_ready"] is True
    assert row["exchange"] == "Nasdaq Stockholm"


def test_pre_revenue_or_negative_earnings_company_cannot_get_high_grade():
    row = evaluate_company(base(
        ticker="BIO.OL",
        sector="Healthcare",
        industry="Biotechnology",
        trailing_eps=None,
        annual_eps=[-5, -4, -3, -2],
        free_cash_flow=-50,
        free_cash_flow_history=[-50, -45, -40, -35],
    ), as_of=NOW)
    assert row["quality_state"] == "INSUFFICIENT"
    assert row["overall_stars"] <= 2


def test_report_identity_puts_exchange_country_and_grade_near_company_name():
    row = evaluate_company(base(exchange="Oslo Børs"), as_of=NOW)
    result = {
        "state": "COMPLETED",
        "generated_at": NOW.isoformat(),
        "run_key": "quality/test",
        "groups": {"Kvalitetsselskap": [row]},
        "quality_v2_shadow": {"rows": [], "evaluated": 0},
    }
    short = build_screen_pdf(result)
    extended = build_extended_analysis_pdf(result)
    for pdf_bytes in (short, extended):
        text = "\n".join(page.extract_text() or "" for page in PdfReader(BytesIO(pdf_bytes)).pages)
        assert "Oslo Børs" in text
        assert "Norway" in text
        assert "P/E ved dagens kurs" in text


def test_grade_is_summary_not_a_replacement_for_sector_logic():
    insurance = evaluate_company(base(
        ticker="INS.OL", sector="Financial Services", industry="Insurance",
        is_financial=True, roce=None, roce_history=[], roe_history=[.20,.19,.18,.17],
    ), as_of=NOW)
    utility = evaluate_company(base(
        ticker="UTL.OL", sector="Utilities", industry="Electric Utilities",
        roce=.09, roce_history=[.09,.085,.08,.075],
    ), as_of=NOW)
    shipping = evaluate_company(base(
        ticker="SEA.OL", sector="Industrials", industry="Marine Shipping",
        roce=.11, roce_history=[.11,.10,.09,.08],
    ), as_of=NOW)
    assert {insurance["sector_policy"], utility["sector_policy"], shipping["sector_policy"]} == {
        "FINANCIAL", "CAPITAL_INTENSIVE", "CYCLICAL"
    }
    assert insurance["grade_method"] == utility["grade_method"] == shipping["grade_method"]
