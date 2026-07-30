#!/usr/bin/env python3
"""Render build smoke for critical imports and PDF round-trip integrity."""
from __future__ import annotations

import io
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from runtime_dependencies import assert_runtime_dependencies  # noqa: E402


def run_smoke() -> dict:
    dependency_status = assert_runtime_dependencies()

    from pypdf import PdfReader
    from reportlab.pdfgen import canvas

    buffer = io.BytesIO()
    document = canvas.Canvas(buffer)
    marker = "V19.14.6 PDF DEPENDENCY SMOKE OK"
    document.drawString(72, 720, marker)
    document.save()
    pdf_bytes = buffer.getvalue()
    reader = PdfReader(io.BytesIO(pdf_bytes))
    extracted = "\n".join(page.extract_text() or "" for page in reader.pages)
    if marker not in extracted:
        raise RuntimeError("pypdf kunne importeres, men PDF-rundtesten mistet kontrollteksten")
    return {
        "ok": True,
        "dependency_status": dependency_status,
        "pdf_pages": len(reader.pages),
        "pdf_size": len(pdf_bytes),
        "marker_found": True,
    }


def main() -> int:
    try:
        result = run_smoke()
    except Exception as exc:
        print(json.dumps({"ok": False, "error": f"{type(exc).__name__}: {exc}"}, ensure_ascii=False))
        return 1
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
