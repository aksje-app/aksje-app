from __future__ import annotations
import io, json, zipfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]

def test_ui_exposes_all_shareable_artifacts():
    src=(ROOT/"quality_valuation_ui.py").read_text(encoding="utf-8")
    assert ("Last ned / del kort PDF" in src or "Åpne / del kort PDF" in src or '"Kort rapport"' in src)
    assert ("Last ned / del utvidet PDF" in src or "Åpne / del utvidet PDF" in src or '"Full analyse"' in src)
    assert ("Last ned / del diagnose" in src or "Åpne / kopier diagnose" in src or '"Diagnose"' in src)
    assert ("Last ned / del komplett kontrollpakke" in src or "Åpne / del komplett kontrollpakke" in src or '"Last ned alt"' in src)
    assert ("⌂ Hovedsiden" in src or "← Tilbake til Kvalitet" in src)
    assert ('_absolute_report_return_url("overview")' in src or '_absolute_report_return_url("quality_reports")' in src)

def test_extended_pdf_returns_to_app_context():
    src=(ROOT/"quality_extended_report.py").read_text(encoding="utf-8")
    assert "add_pdf_return_links" in src
    assert ('_absolute_report_return_url("overview")' in src or '_absolute_report_return_url("quality_reports")' in src)

def test_public_report_has_app_return():
    src=(ROOT/"public_report_ui.py").read_text(encoding="utf-8")
    assert '"overview"' in src
    assert ("← Hovedsiden" in src or "← Tilbake til rapportvalg" in src)


def test_package_builder_names_same_run_artifacts():
    src=(ROOT/"quality_report_package.py").read_text(encoding="utf-8")
    for name in ("kort_rapport.pdf","utvidet_analyse.pdf","diagnose.json","manifest.json"):
        assert name in src
    assert "quality-manual-report-package@1.0" in src
