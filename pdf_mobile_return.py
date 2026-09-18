"""Add a visible, clickable route back to Aurora inside generated PDFs."""
from __future__ import annotations

from io import BytesIO
from urllib.parse import urlsplit


RETURN_LABEL = "Tilbake til AI Aksje Analyzer"


def _safe_app_url(value: str) -> str:
    parsed = urlsplit(str(value or "").strip())
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise ValueError("Returadressen må være en absolutt HTTP(S)-adresse")
    return str(value).strip()


def add_pdf_return_links(pdf_bytes: bytes, *, return_url: str) -> bytes:
    """Overlay a return link at the top and bottom of every PDF page.

    The link lives in the PDF itself.  It therefore remains available in the
    iOS/Android PDF viewer even when the browser has replaced the app page.
    """
    from pypdf import PdfReader, PdfWriter
    from pypdf.annotations import Link
    from reportlab.pdfgen import canvas

    data = bytes(pdf_bytes)
    if not data.startswith(b"%PDF-"):
        raise ValueError("Ugyldig PDF")
    target = _safe_app_url(return_url)
    reader = PdfReader(BytesIO(data))
    writer = PdfWriter()

    for page_number, page in enumerate(reader.pages):
        width = float(page.mediabox.width)
        height = float(page.mediabox.height)
        overlay_buffer = BytesIO()
        overlay = canvas.Canvas(overlay_buffer, pagesize=(width, height))
        overlay.setFillColorRGB(0.02, 0.42, 0.70)
        overlay.roundRect(14, height - 27, 190, 19, 4, fill=1, stroke=0)
        overlay.roundRect(14, 4, 190, 19, 4, fill=1, stroke=0)
        overlay.setFillColorRGB(1, 1, 1)
        overlay.setFont("Helvetica-Bold", 8)
        overlay.drawString(22, height - 21, f"< {RETURN_LABEL}")
        overlay.drawString(22, 10, f"< {RETURN_LABEL}")
        overlay.save()
        overlay_buffer.seek(0)
        page.merge_page(PdfReader(overlay_buffer).pages[0])
        writer.add_page(page)
        writer.add_annotation(
            page_number=page_number,
            annotation=Link(rect=(14, height - 27, 204, height - 8), url=target),
        )
        writer.add_annotation(
            page_number=page_number,
            annotation=Link(rect=(14, 4, 204, 23), url=target),
        )

    output = BytesIO()
    writer.write(output)
    return output.getvalue()


__all__ = ["RETURN_LABEL", "add_pdf_return_links"]
