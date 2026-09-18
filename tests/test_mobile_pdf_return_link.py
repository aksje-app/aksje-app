from __future__ import annotations

from io import BytesIO

import pytest
from pypdf import PdfReader
from reportlab.pdfgen import canvas

import pdf_mobile_return
import public_report_ui
from app_version import APP_VERSION, PREVIOUS_APP_VERSION


def _pdf(page_count: int = 2) -> bytes:
    output = BytesIO()
    document = canvas.Canvas(output, pagesize=(300, 400))
    for number in range(page_count):
        document.drawString(40, 200, f"Rapportside {number + 1}")
        document.showPage()
    document.save()
    return output.getvalue()


def test_return_link_is_visible_and_clickable_on_every_pdf_page():
    target = "https://aksje-app.onrender.com/?aa_nav=portfolio"
    result = pdf_mobile_return.add_pdf_return_links(_pdf(), return_url=target)
    reader = PdfReader(BytesIO(result))

    assert len(reader.pages) == 2
    for page in reader.pages:
        assert page.extract_text().count(pdf_mobile_return.RETURN_LABEL) == 2
        links = [item.get_object()["/A"]["/URI"] for item in page["/Annots"]]
        assert links == [target, target]


def test_pdf_return_link_rejects_external_non_http_targets():
    with pytest.raises(ValueError):
        pdf_mobile_return.add_pdf_return_links(_pdf(1), return_url="javascript:alert(1)")


def test_public_pdf_hydration_embeds_selected_program_route(monkeypatch, tmp_path):
    import report_delivery

    monkeypatch.setattr(report_delivery, "PUBLIC_REPORT_DIR", tmp_path)
    monkeypatch.setenv("RENDER_EXTERNAL_URL", "https://aksje-app.onrender.com")
    token = "A" * 43
    target, _ = public_report_ui._hydrate_static_pdf(
        token, {"data": _pdf(1), "_return_to": "portfolio"}
    )
    reader = PdfReader(BytesIO(target.read_bytes()))
    links = [item.get_object()["/A"]["/URI"] for item in reader.pages[0]["/Annots"]]
    assert links == ["https://aksje-app.onrender.com/?aa_nav=portfolio"] * 2


def test_absolute_return_url_is_allowlisted(monkeypatch):
    monkeypatch.setenv("RENDER_EXTERNAL_URL", "https://aksje-app.onrender.com/path")
    assert public_report_ui._absolute_report_return_url("portfolio") == (
        "https://aksje-app.onrender.com/?aa_nav=portfolio"
    )
    assert public_report_ui._absolute_report_return_url("https://evil.invalid") == (
        "https://aksje-app.onrender.com/?aa_nav=reports"
    )


def test_mobile_pdf_return_release_has_new_canonical_version():
    assert APP_VERSION == "v19.22.0-rc16.32p"
    assert PREVIOUS_APP_VERSION == "v19.22.0-rc16.32o"
