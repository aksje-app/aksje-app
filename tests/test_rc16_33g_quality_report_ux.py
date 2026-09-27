from __future__ import annotations

from io import BytesIO
from pathlib import Path

from pypdf import PdfReader

from public_report_ui import (
    _report_landing_actions,
    _report_return_href,
    _return_label,
)
from quality_valuation_ui import _quality_report_choice_cards, build_screen_pdf


def test_report_selector_uses_text_cards_and_quality_return():
    html = _quality_report_choice_cards({
        "short_pdf": "a" * 40,
        "extended_pdf": "b" * 40,
        "diagnosis": "c" * 40,
        "package": "d" * 40,
    })
    assert "Kort rapport" in html
    assert "Full analyse" in html
    assert "Diagnose" in html
    assert "Last ned alt" in html
    assert "← Tilbake til Kvalitet" in html
    assert "ANBEFALT" in html
    assert "public_report_token=" in html
    assert "return_to=quality_reports" in html
    assert "📄" not in html and "📊" not in html and "🧾" not in html and "📦" not in html


def test_report_page_returns_to_report_selector_not_overview():
    href = _report_return_href("quality_reports")
    assert "aa_nav=quality_valuation" in href
    assert "qv_reports=1" in href
    assert _return_label("quality_reports") == "← Tilbake til rapportvalg"


def test_mobile_report_page_has_clear_print_action_and_no_technical_path():
    html = _report_landing_actions(
        "/app/static/reports/public_report_test.pdf",
        return_href="/?aa_nav=quality_valuation&qv_reports=1",
        return_label="← Tilbake til rapportvalg",
    )
    assert "Skriv ut PDF" in html
    assert "Del / åpne PDF" in html
    assert "Tilbake til rapportvalg" in html
    assert "/app/static/reports/public_report_test.pdf" in html  # href/iframe only
    assert "varig lenke" not in html
    assert "Reserve: direkte nedlasting" not in html


def test_quality_pdf_return_annotation_targets_report_selector_and_is_nonprinting(monkeypatch):
    monkeypatch.setenv("RENDER_EXTERNAL_URL", "https://example.test")
    result = {
        "state": "COMPLETED",
        "generated_at": "2026-09-27T03:00:00+00:00",
        "run_key": "quality/test",
        "groups": {},
    }
    pdf = build_screen_pdf(result)
    reader = PdfReader(BytesIO(pdf))
    annots = reader.pages[0].get("/Annots") or []
    assert annots
    annotation = annots[0].get_object()
    uri = str((annotation.get("/A") or {}).get("/URI") or "")
    assert "aa_nav=quality_valuation" in uri
    assert "qv_reports=1" in uri
    assert int(annotation.get("/F", 0)) & 4 == 0


def test_old_ambiguous_primary_controls_removed_from_quality_ui():
    src = Path("quality_valuation_ui.py").read_text(encoding="utf-8")
    for old in (
        "Åpne / del kort PDF",
        "Åpne / del utvidet PDF",
        "Åpne / kopier diagnose",
        "Åpne / del komplett kontrollpakke",
        "PDF-returknappen er skjerm-only",
        'st.button("⌂ Hovedsiden"',
    ):
        assert old not in src
