from pathlib import Path

from market_intelligence import _localize_report_decimal_text
from report_integrity import canonical_report_view, validate_report_integrity


def _candidate(ticker: str, score: float) -> dict:
    return {
        "ticker": ticker,
        "market": "Norge",
        "investment_score": score,
        "risk_score": 30,
        "data_quality": 95,
        "valid_for_decision": True,
        "evidence_valid_for_decision": False,
        "portfolio_action": "REVIEW",
        "raw": {},
    }


def test_candidate_outcome_accounting_is_a_hard_integrity_gate():
    report = canonical_report_view({
        "run_id": "MI-RC16-32",
        "created_at": "2026-08-10T10:00:00+02:00",
        "summary": {"scanned": 2},
        "candidates": [_candidate("AAA.OL", 75.14), _candidate("BBB.OL", 68.3)],
        "data_quality": {"score": 100},
    })
    assert validate_report_integrity(report)["ok"] is True
    report["report_summary"]["manual_review"] += 1
    result = validate_report_integrity(report)
    assert result["ok"] is False
    assert any("Kandidatregnskapet er ikke avstemt" in error for error in result["errors"])


def test_norwegian_decimal_format_preserves_versions_ids_and_urls():
    text = _localize_report_decimal_text(
        "Score 74.49, risiko 65.0. Versjon v19.22.0, schema 1.6 og https://x.no/v1.2/a."
    )
    assert "74,49" in text
    assert "65,0" in text
    assert "v19.22.0" in text
    assert "https://x.no/v1.2/a" in text


def test_pdf_source_contains_user_facing_reconciliation_and_no_machine_stamp():
    source = Path("market_intelligence.py").read_text(encoding="utf-8")
    assert "Kandidatavstemming:" in source
    assert "undersøkes manuelt" in source
    assert "Datakontroll: aktualitet og gyldighet" in source
    assert "Kandidatfunn og datagrunnlag" in source
    assert "INTEGRITY-CANDIDATES=" not in source
    assert 'Paragraph("Freshness & Data Contract"' not in source
    assert 'Paragraph("Discovery & Data Layer"' not in source

