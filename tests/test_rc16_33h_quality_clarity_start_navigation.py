from __future__ import annotations

from io import BytesIO
from pathlib import Path

from pypdf import PdfReader

from quality_model_v2 import summarize_shadow
from quality_valuation_ui import _valuation_blocks_html, build_screen_pdf
from quality_extended_report import build_extended_analysis_pdf
from ui_library.shell import DESKTOP_ROUTES, MOBILE_ROUTES, _LEGACY_TARGETS


def _afg_like_row():
    return {
        "ticker": "AFG.OL",
        "name": "AF Gruppen ASA",
        "exchange": "Oslo Børs",
        "country": "Norway",
        "currency": "NOK",
        "price": 197.20,
        "group": "Kvalitetsselskap",
        "quality_state": "QUALITY",
        "quality_evidence_ready": True,
        "overall_stars": 4,
        "overall_grade_label": "Sterk",
        "overall_grade_color": "#16a34a",
        "quality_score": 4,
        "quality_color": "#16a34a",
        "valuation_score": 3,
        "valuation_color": "#d97706",
        "trend_score": 3,
        "trend_color": "#d97706",
        "data_score": 5,
        "data_color": "#0b6b3a",
        "why_now": "Hvorfor nå: sektorjustert kvalitet er sterk.",
        "grade_confidence": "HØY",
        "next_star_requirement": "For neste stjerne: bedre dokumentert prisingsmargin.",
        "reported_pe": 17.93,
        "forward_pe": 15.58,
        "normalized_pe": 25.48,
        "normalized_eps": 7.74,
        "assumed_pe": 24.94,
        "fair_price_scenario": 193.04,
        "entry_range_scenario": [164.08, 193.04],
        "valuation_position_text": "Dagens kurs er 2.2% over scenarioverdien.",
        "valuation_position_color": "#d97706",
        "peer_count": 3,
        "peer_basis_quality": "THIN",
        "peer_tickers": ["VEI.OL", "SNTIA.OL", "GOD.OL"],
        "peer_normalized_pe": [24.94, 17.82, 116.0],
        "sector_policy": "STANDARD",
        "roce_pct": 18.0,
        "roce_latest_pct": 19.0,
        "roce_trend": "STABIL",
        "roce_history_pct": [19.0, 18.0, 17.0],
        "annual_eps_history": [10.0, 7.74, 7.0],
        "fiscal_periods": ["2025", "2024", "2023"],
        "free_cash_flow_history": [100, 90, 80],
        "debt_history": [200, 190, 180],
        "operating_margin_history": [.12, .11, .10],
        "warnings": [],
    }


def test_price_and_pe_are_visually_separate_and_multiples_have_x():
    html = _valuation_blocks_html(_afg_like_row())
    assert "KURS / PRIS" in html
    assert ("Kurs nå: 197.20 NOK" in html or "Kurs nå: 197,20 NOK" in html)
    assert ("Scenarioverdi: 193.04 NOK" in html or "Scenarioverdi: 193,04 NOK" in html)
    assert ("Inngangsscenario: 164.08 NOK" in html or "Inngangsscenario: 164,08 NOK" in html)
    assert "VERDSETTELSE" in html
    assert ("P/E ved dagens kurs: 17.93x" in html or "P/E ved dagens kurs: 17,93x" in html)
    assert ("Normalisert P/E ved dagens kurs: 25.48x" in html or "Normalisert P/E ved dagens kurs: 25,48x" in html)
    assert ("Peer-median P/E: 24.94x" in html or "Peer-median P/E: 24,94x" in html)
    assert "P/E er multipler, ikke aksjekurs." in html
    assert "Peer-grunnlag: 3 selskaper · TYNT GRUNNLAG" in html


def test_short_and_full_pdf_keep_price_separate_from_multiples():
    row = _afg_like_row()
    result = {
        "state": "COMPLETED",
        "generated_at": "2026-09-27T12:00:00+00:00",
        "run_key": "quality/test",
        "groups": {"Kvalitetsselskap": [row]},
        "quality_v2_shadow": {"rows": [], "evaluated": 0},
        "quality_v2_oversight": {},
    }
    for pdf in (build_screen_pdf(result), build_extended_analysis_pdf(result)):
        text = "\n".join(page.extract_text() or "" for page in PdfReader(BytesIO(pdf)).pages)
        assert "KURS / PRIS" in text
        assert "VERDSETTELSE" in text
        assert ("197.20 NOK" in text or "197,20 NOK" in text)
        assert ("25.48x" in text or "25,48x" in text)
        assert "SCENARIO" in text.upper()


def test_v2_disagreements_are_split_into_weaker_and_stronger_tickers():
    summary = summarize_shadow([
        {"ticker": "WEAK.OL", "comparison_direction": "V2_WEAKER", "quality_band": "WATCH", "reasons": []},
        {"ticker": "STRONG.OL", "comparison_direction": "V2_STRONGER", "quality_band": "STRONG", "reasons": []},
        {"ticker": "SAME.OL", "comparison_direction": "SAME", "quality_band": "STABLE_QUALITY", "reasons": []},
    ])
    assert summary["disagreement_count"] == 2
    assert summary["v2_weaker_count"] == 1
    assert summary["v2_stronger_count"] == 1
    assert summary["v2_weaker_tickers"] == ["WEAK.OL"]
    assert summary["v2_stronger_tickers"] == ["STRONG.OL"]
    assert summary["comparison_complete"] is True
    assert summary["v2_weaker_count"] + summary["v2_stronger_count"] == summary["disagreement_count"]


def test_overview_explains_same_disagreements_and_keeps_technical_weakening_separate():
    src = Path("pages/overview.py").read_text(encoding="utf-8")
    assert ("AV DISSE: V2 SVAKERE" in src or "V2 SVAKERE" in src)
    assert ("AV DISSE: V2 STERKERE" in src or "V2 STERKERE" in src)
    assert "Vis hvilke aksjer V1.1 og V2 er uenige om" in src
    assert ("Teknisk trend:" in src or ">Teknisk trend<" in src)
    assert "ikke det samme som V2 svakere enn aktiv modell" in src


def test_start_button_is_direct_on_mobile_and_desktop_navigation():
    assert DESKTOP_ROUTES[0].label == "Start"
    assert MOBILE_ROUTES[0].label == "Start"
    assert DESKTOP_ROUTES[0].slug == "overview"
    assert MOBILE_ROUTES[0].slug == "overview"
    assert _LEGACY_TARGETS["overview"] == "dashboard"


def test_previous_run_comparison_is_persisted_for_stars_quality_price_and_group():
    src = Path("quality_valuation_store.py").read_text(encoding="utf-8")
    for field in (
        "previous_overall_stars",
        "star_delta",
        "quality_score_delta",
        "valuation_score_delta",
        "group_changed",
    ):
        assert field in src


def test_sector_robustness_gate_is_still_part_of_release_path():
    src = Path("quality_valuation.py").read_text(encoding="utf-8")
    for policy in ("FINANCIAL", "REAL_ESTATE", "CYCLICAL", "CAPITAL_INTENSIVE", "STANDARD"):
        assert policy in src
