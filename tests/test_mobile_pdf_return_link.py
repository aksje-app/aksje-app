from __future__ import annotations

from io import BytesIO

import pytest
from pypdf import PdfReader
from reportlab.pdfgen import canvas

import pdf_mobile_return
import public_report_ui
from mobile_file_delivery import render_mobile_file_delivery
from app_version import APP_VERSION, PREVIOUS_APP_VERSION


def _pdf(page_count: int = 2) -> bytes:
    output = BytesIO()
    document = canvas.Canvas(output, pagesize=(300, 400))
    for number in range(page_count):
        document.drawString(40, 200, f"Rapportside {number + 1}")
        document.showPage()
    document.save()
    return output.getvalue()


def test_single_screen_only_link_and_no_printed_button():
    target = "https://aksje-app.onrender.com/?aa_nav=portfolio"
    result = pdf_mobile_return.add_pdf_return_links(_pdf(), return_url=target)
    reader = PdfReader(BytesIO(result))

    assert len(reader.pages) == 2
    assert all(pdf_mobile_return.RETURN_LABEL not in (page.extract_text() or "") for page in reader.pages)
    assert len(reader.pages[0]["/Annots"]) == 2  # One visual label and one link.
    assert "/Annots" not in reader.pages[1] or len(reader.pages[1]["/Annots"]) == 0
    label, link = (item.get_object() for item in reader.pages[0]["/Annots"])
    assert label["/Subtype"] == "/FreeText"
    assert int(label["/F"]) & 4 == 0
    assert label["/AP"]["/N"].get_object().get_data()
    assert link["/Subtype"] == "/Link"
    assert link["/A"]["/URI"] == target
    assert int(link["/F"]) & 4 == 0  # PDF Print annotation flag is absent.


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
    links = [item.get_object()["/A"]["/URI"] for item in reader.pages[0]["/Annots"] if "/A" in item.get_object()]
    assert links == ["https://aksje-app.onrender.com/?aa_nav=portfolio"]


def test_absolute_return_url_is_allowlisted(monkeypatch):
    monkeypatch.setenv("RENDER_EXTERNAL_URL", "https://aksje-app.onrender.com/path")
    assert public_report_ui._absolute_report_return_url("portfolio") == (
        "https://aksje-app.onrender.com/?aa_nav=portfolio"
    )
    assert public_report_ui._absolute_report_return_url("https://evil.invalid") == (
        "https://aksje-app.onrender.com/?aa_nav=reports"
    )


def test_report_delivery_shows_no_extra_return_button():
    class Page:
        blocks = []

        def markdown(self, value, **kwargs):
            self.blocks.append(value)

        def caption(self, value):
            pass

        def code(self, value, **kwargs):
            pass

    page = Page()
    render_mobile_file_delivery(
        page, url="/app/static/reports/example.pdf", filename="example.pdf",
        label="Åpne PDF", mime="application/pdf", key="example", show_return=False,
    )
    assert "Tilbake til programmet" not in "\n".join(page.blocks)
    assert public_report_ui._report_landing_actions("/app/static/reports/example.pdf").count(
        "Tilbake til programmet"
    ) == 1


def test_mobile_pdf_return_release_has_new_canonical_version():
    assert APP_VERSION == "v19.22.0-rc16.32t"
    assert PREVIOUS_APP_VERSION == "v19.22.0-rc16.32s"
