"""Build one portable artifact containing the exact manual Quality run outputs."""
from __future__ import annotations
from io import BytesIO
import json
from typing import Any, Mapping
from zipfile import ZIP_DEFLATED, ZipFile


def build_manual_report_package(result: Mapping[str, Any]) -> bytes:
    from quality_valuation_ui import build_screen_pdf, diagnostic_document
    from quality_extended_report import build_extended_analysis_pdf

    run_id = str(result.get("run_key") or result.get("report_id") or "manual_run").replace("/", "_")
    short_pdf = build_screen_pdf(result)
    extended_pdf = build_extended_analysis_pdf(result)
    diagnosis = diagnostic_document(result)
    manifest = {
        "schema": "quality-manual-report-package@1.0",
        "run_id": result.get("run_key"),
        "generated_at": result.get("generated_at"),
        "app_version": __import__("app_version").APP_VERSION,
        "files": ["kort_rapport.pdf", "utvidet_analyse.pdf", "diagnose.json"],
        "purpose": "Samlet kontrollpakke: alle artefakter stammer fra samme manuelle kjøring.",
    }
    out=BytesIO()
    with ZipFile(out,"w",ZIP_DEFLATED) as z:
        z.writestr("kort_rapport.pdf", short_pdf)
        z.writestr("utvidet_analyse.pdf", extended_pdf)
        z.writestr("diagnose.json", diagnosis)
        z.writestr("manifest.json", json.dumps(manifest,ensure_ascii=False,indent=2).encode("utf-8"))
    return out.getvalue()


__all__=["build_manual_report_package"]
