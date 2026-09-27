from __future__ import annotations

from io import BytesIO
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

from pypdf import PdfReader
from reportlab.pdfgen import canvas

from pdf_mobile_return import add_pdf_return_links
from public_report_ui import _report_return_href, _return_query
from quality_stability_contract import (
    QUALITY_REPORTS_RETURN,
    is_supported_deep_link_nav,
    validate_quality_row,
    validate_report_return_query,
    validate_v2_summary,
)
from quality_valuation import _enforce_semantic_consistency


def _three_page_pdf() -> bytes:
    buf = BytesIO()
    pdf = canvas.Canvas(buf)
    for i in range(3):
        pdf.drawString(72, 720, f"Side {i+1}")
        pdf.showPage()
    pdf.save()
    return buf.getvalue()


def test_quality_report_return_route_is_accepted_by_main_router_contract():
    assert QUALITY_REPORTS_RETURN == {"aa_nav": "quality_valuation", "qv_reports": "1"}
    assert is_supported_deep_link_nav("quality_valuation")
    assert validate_report_return_query(QUALITY_REPORTS_RETURN) == []
    href = _report_return_href("quality_reports")
    parsed = parse_qs(urlsplit(href).query)
    assert parsed["aa_nav"] == ["quality_valuation"]
    assert parsed["qv_reports"] == ["1"]


def test_app_uses_central_deep_link_contract_not_private_hardcoded_allowlist():
    src = Path("app.py").read_text(encoding="utf-8")
    assert "from quality_stability_contract import is_supported_deep_link_nav" in src
    assert "if is_supported_deep_link_nav(nav_from_url):" in src
    assert 'nav_from_url in {"dashboard"' not in src


def test_pdf_return_link_exists_on_every_page_and_is_nonprinting():
    pdf = add_pdf_return_links(
        _three_page_pdf(),
        return_url="https://example.test/?aa_nav=quality_valuation&qv_reports=1",
    )
    reader = PdfReader(BytesIO(pdf))
    assert len(reader.pages) == 3
    for page in reader.pages:
        annots = [ref.get_object() for ref in (page.get("/Annots") or [])]
        links = [a for a in annots if str(a.get("/Subtype") or "") == "/Link"]
        assert links, "Every PDF page must have a return link"
        uri = str((links[0].get("/A") or {}).get("/URI") or "")
        assert "aa_nav=quality_valuation" in uri
        assert "qv_reports=1" in uri
        assert all(int(a.get("/F", 0)) & 4 == 0 for a in annots)


def test_diagnosis_and_zip_open_external_view_only_from_in_app_landing():
    src = Path("public_report_ui.py").read_text(encoding="utf-8")
    assert "_hydrate_static_file(file_token, artifact)" in src
    assert 'target="_blank"' in src
    assert "Appens rapportvalg blir stående i denne fanen." in src
    assert "Direkte nedlasting" in src
    assert "_return_to_report_choices(st, return_to)" in src


def test_quality_semantic_invariants_are_hard_fail_rules():
    assert validate_quality_row({
        "group": "Kvalitetsselskap",
        "quality_state": "QUALITY",
        "review_reason_category": "QUALITY_CONFIRMED",
        "overall_stars": 5,
        "quality_score": 5,
        "valuation_score": 3,
        "trend_score": 5,
        "data_score": 5,
    }) == ["5_STARS_WITH_WEAK_SUBSCORE"]

    errors = validate_quality_row({
        "group": "Kvalitetsselskap",
        "quality_state": "IMPROVING",
        "review_reason_category": "QUALITY_WEAK",
        "overall_stars": 3,
        "quality_score": 2,
        "valuation_score": 3,
        "trend_score": 4,
        "data_score": 5,
    })
    assert "QUALITY_STATE_REASON_CONTRADICTION" in errors
    assert "QUALITY_GROUP_WITH_LOW_QUALITY_SCORE" in errors


def test_low_quality_score_cannot_remain_quality_company_or_candidate():
    row = {"group": "Kvalitetsselskap", "quality_score": 2, "warnings": []}
    _enforce_semantic_consistency(row)
    assert row["group"] == "Ufullstendig / krever vurdering"

    row = {"group": "Attraktivt priset kandidat", "quality_score": 1, "warnings": []}
    _enforce_semantic_consistency(row)
    assert row["group"] == "Ufullstendig / krever vurdering"


def test_v2_classification_sum_is_an_invariant_when_available():
    assert validate_v2_summary({
        "classification_available": True,
        "classification_schema": "quality_v2_direction@1",
        "disagreement_count": 5,
        "v2_weaker_count": 3,
        "v2_stronger_count": 2,
        "v2_weaker_tickers": ["A.OL", "B.OL", "C.OL"],
        "v2_stronger_tickers": ["D.OL", "E.OL"],
    }) == []
    errors = validate_v2_summary({
        "classification_available": True,
        "classification_schema": "quality_v2_direction@1",
        "disagreement_count": 5,
        "v2_weaker_count": 0,
        "v2_stronger_count": 0,
        "v2_weaker_tickers": [],
        "v2_stronger_tickers": [],
    })
    assert "V2_DISAGREEMENT_SUM_MISMATCH" in errors


def test_report_selector_contract_is_preserved():
    assert _return_query("quality_reports") == QUALITY_REPORTS_RETURN
    ui = Path("quality_valuation_ui.py").read_text(encoding="utf-8")
    for token in ("short_pdf", "extended_pdf", "diagnosis", "package"):
        assert token in ui
    assert ui.count("return_to=quality_reports") >= 4
