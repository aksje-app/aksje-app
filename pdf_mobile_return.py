"""Add one screen-only route back to Aurora inside a viewed PDF."""
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
    """Attach one clickable, nonprinting return control to the first page.

    An annotation appearance is visible in PDF viewers, while its absent Print
    flag keeps the control off paper. No return graphics enter page content.
    """
    from pypdf import PdfReader, PdfWriter
    from pypdf.annotations import FreeText, Link
    from pypdf.generic import (
        ArrayObject, DecodedStreamObject, DictionaryObject, NameObject, NumberObject,
    )

    data = bytes(pdf_bytes)
    if not data.startswith(b"%PDF-"):
        raise ValueError("Ugyldig PDF")
    target = _safe_app_url(return_url)
    reader = PdfReader(BytesIO(data))
    writer = PdfWriter()

    for page in reader.pages:
        writer.add_page(page)

    if reader.pages:
        height = float(reader.pages[0].mediabox.height)
        appearance = DecodedStreamObject()
        appearance.set_data(
            b"q 0.02 0.42 0.70 rg 0 0 190 19 re f "
            b"1 1 1 rg BT /F1 8 Tf 8 6 Td "
            b"(< Tilbake til AI Aksje Analyzer) Tj ET Q"
        )
        appearance.update({
            NameObject("/Type"): NameObject("/XObject"),
            NameObject("/Subtype"): NameObject("/Form"),
            NameObject("/BBox"): ArrayObject([NumberObject(0), NumberObject(0), NumberObject(190), NumberObject(19)]),
            NameObject("/Resources"): DictionaryObject({
                NameObject("/Font"): DictionaryObject({
                    NameObject("/F1"): DictionaryObject({
                        NameObject("/Type"): NameObject("/Font"),
                        NameObject("/Subtype"): NameObject("/Type1"),
                        NameObject("/BaseFont"): NameObject("/Helvetica-Bold"),
                    }),
                }),
            }),
        })
        link = Link(rect=(14, height - 27, 204, height - 8), url=target)
        link[NameObject("/F")] = NumberObject(0)  # Visible on screen, not in print.
        label = FreeText(
            text=f"< {RETURN_LABEL}", rect=(14, height - 27, 204, height - 8),
            font="Helvetica", bold=True, font_size="8pt",
            font_color="ffffff", background_color="066bb3", border_color=None,
        )
        label[NameObject("/F")] = NumberObject(0)
        label[NameObject("/AP")] = DictionaryObject({NameObject("/N"): writer._add_object(appearance)})
        writer.add_annotation(page_number=0, annotation=label)
        writer.add_annotation(page_number=0, annotation=link)

    output = BytesIO()
    writer.write(output)
    return output.getvalue()


__all__ = ["RETURN_LABEL", "add_pdf_return_links"]
