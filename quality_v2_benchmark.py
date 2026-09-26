"""External quality benchmark harness for V2 validation.

The benchmark is a reference set only. External ratings/stars/fair values are
not copied into Autonomi and never affect production recommendations.
"""
from __future__ import annotations
from typing import Any, Mapping, Sequence

REFERENCE_NAME = "Morningstar Nordic Wide-Moat reference set"
REFERENCE_AS_OF = "2026-09"
REFERENCE_SYMBOLS = (
    "ALFA.ST", "ASSA-B.ST", "ATCO-A.ST", "EKTAB.ST", "EPI-A.ST", "KNEBV.HE",
    "KOG.OL", "METSO.HE", "NOVO-B.CO", "NSIS-B.CO", "SAAB-B.ST", "SAND.ST",
    "SKF-B.ST", "WRT1V.HE",
)


def compare_reference(rows: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    by_ticker = {str(row.get("ticker") or "").upper(): dict(row) for row in rows}
    present = [ticker for ticker in REFERENCE_SYMBOLS if ticker in by_ticker]
    missing = [ticker for ticker in REFERENCE_SYMBOLS if ticker not in by_ticker]
    bands: dict[str, int] = {}
    for ticker in present:
        band = str(by_ticker[ticker].get("quality_band") or "NOT_DOCUMENTED")
        bands[band] = bands.get(band, 0) + 1
    return {
        "benchmark": REFERENCE_NAME,
        "reference_as_of": REFERENCE_AS_OF,
        "purpose": "External validation reference only; not an investment ranking or recommendation.",
        "production_effect": False,
        "reference_count": len(REFERENCE_SYMBOLS),
        "matched_count": len(present),
        "missing_symbols": missing,
        "quality_band_counts": bands,
    }
