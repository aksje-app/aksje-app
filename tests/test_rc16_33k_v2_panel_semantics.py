from __future__ import annotations

from pathlib import Path

from quality_stability_contract import validate_v2_summary
from quality_v2_shadow_store import build_shadow_comparison


SCHEMA = "quality_v2_direction@1"
MODEL = "quality_v2@2.0-shadow"


def _summary(weaker, stronger):
    weaker = list(weaker)
    stronger = list(stronger)
    return {
        "classification_available": True,
        "classification_schema": SCHEMA,
        "model_version": MODEL,
        "comparison_complete": True,
        "disagreement_count": len(weaker) + len(stronger),
        "v2_weaker_count": len(weaker),
        "v2_stronger_count": len(stronger),
        "v2_weaker_tickers": weaker,
        "v2_stronger_tickers": stronger,
    }


def test_first_compatible_classification_does_not_claim_all_are_new():
    current = _summary([], [
        "VEI.OL", "SNTIA.OL", "AFG.OL", "FRO.OL", "ABG.OL", "MEDI.OL",
        "HAFNI.OL", "BWLPG.OL", "ATEA.OL", "VAR.OL", "EQNR.OL", "PROT.OL", "ITERA.OL",
    ])
    previous = {
        "complete_runs": 4,
        "disagreement_count": 5,
        # Legacy state: no schema, no complete direction ticker lists.
    }
    result = build_shadow_comparison(previous, current)
    assert result["comparison_available"] is False
    assert result["comparison_reason"] in {
        "PREVIOUS_CLASSIFICATION_UNAVAILABLE",
        "CLASSIFICATION_SCHEMA_MISMATCH",
    }
    assert result["new_disagreement_tickers"] == []
    assert result["resolved_disagreement_tickers"] == []
    assert result["unchanged_disagreement_tickers"] == []


def test_next_compatible_run_can_report_one_new_two_resolved_eleven_unchanged():
    previous_names = [f"T{i}.OL" for i in range(1, 14)]
    current_names = [f"T{i}.OL" for i in range(1, 12)] + ["NEW.OL"]
    previous = _summary([], previous_names)
    current = _summary([], current_names)

    result = build_shadow_comparison(previous, current)
    assert result["comparison_available"] is True
    assert result["new_disagreement_tickers"] == ["NEW.OL"]
    assert result["resolved_disagreement_tickers"] == ["T12.OL", "T13.OL"]
    assert len(result["unchanged_disagreement_tickers"]) == 11


def test_model_or_schema_change_blocks_historical_change_claims():
    previous = _summary([], ["A.OL"])
    current = _summary([], ["A.OL", "B.OL"])
    previous["model_version"] = "quality_v2@old"
    result = build_shadow_comparison(previous, current)
    assert result["comparison_available"] is False
    assert result["comparison_reason"] == "MODEL_VERSION_MISMATCH"

    previous = _summary([], ["A.OL"])
    previous["classification_schema"] = "quality_v2_direction@old"
    result = build_shadow_comparison(previous, current)
    assert result["comparison_available"] is False
    assert result["comparison_reason"] == "CLASSIFICATION_SCHEMA_MISMATCH"


def test_v2_summary_checks_counts_unique_tickers_overlap_and_schema():
    valid = _summary(["A.OL"], ["B.OL", "C.OL"])
    assert validate_v2_summary(valid) == []

    bad = _summary(["A.OL"], ["B.OL"])
    bad["disagreement_count"] = 3
    assert "V2_DISAGREEMENT_SUM_MISMATCH" in validate_v2_summary(bad)

    bad = _summary(["A.OL", "A.OL"], ["B.OL"])
    errors = validate_v2_summary(bad)
    assert "V2_TICKER_COUNT_MISMATCH" in errors

    bad = _summary(["A.OL"], ["A.OL"])
    assert "V2_TICKER_DIRECTION_OVERLAP" in validate_v2_summary(bad)

    bad = _summary([], ["A.OL"])
    bad["classification_schema"] = ""
    assert "V2_CLASSIFICATION_SCHEMA_MISSING" in validate_v2_summary(bad)


def test_overview_never_uses_new_resolved_without_comparable_history():
    src = Path("pages/overview.py").read_text(encoding="utf-8")
    assert 'history_comparable = bool(v2_shadow.get("comparison_available", False))' in src
    assert "Ingen sammenlignbar tidligere klassifisering" in src
    assert "uendret siden forrige sammenlignbare kjøring" in src
    assert "KOMPLETTE KJØRINGER" in src
    assert "VURDERT I SISTE KJØRING" in src
    assert "Dette betyr ikke i seg selv at aksjen er en bedre investering." in src


def test_mobile_detail_layout_is_readable_not_comma_blob():
    src = Path("pages/overview.py").read_text(encoding="utf-8")
    css = Path("ui_library/theme.py").read_text(encoding="utf-8")
    assert "aa-v2-detail-row" in src
    assert "aa-v2-direction" in src
    assert "aa-v2-technical" in src
    assert "grid-template-columns:1fr" in css
    assert "line-height:1.5" in css


def test_technical_weakening_is_visually_separate_from_model_disagreement():
    src = Path("pages/overview.py").read_text(encoding="utf-8")
    assert '<section class="aa-v2-technical">' in src
    assert "Dette er et eget mål og er ikke det samme som V2 svakere enn aktiv modell." in src
