from __future__ import annotations

from io import BytesIO
from pathlib import Path

from pypdf import PdfReader

import market_intelligence as mi
from investment_pipeline import _source_row_for_reanalysis
from report_integrity import canonical_report_view


def candidate(ticker: str, score: float, *, action: str = "REVIEW", evidence_ready: bool = True) -> dict:
    return {
        "ticker": ticker,
        "name": ticker,
        "market": "USA",
        "rank": 1,
        "investment_score": score,
        "confidence_score": 75,
        "risk_score": 25,
        "trend": "STABIL",
        "score_trend": "STABIL",
        "status": "KREVER MANUELL VURDERING – DOKUMENTASJON" if action != "BUY" else "KJØPSGODKJENT",
        "portfolio_action": action,
        "valid_for_decision": True,
        "evidence_valid_for_decision": evidence_ready,
        "data_quality": 96.67,
        "confidence_profile": {
            "model_confidence": 75,
            "market_data_coverage": 97,
            "documentation_coverage": 45,
            "data_coverage": 45,
            "calibrated_confidence": 55,
            "decision_confidence": 66,
        },
        "decision_readiness": {
            "status": "KOMPLETT" if evidence_ready else "IKKE KOMPLETT",
            "market_data": "GYLDIG",
            "news": "CHECKED_NO_EVENTS",
            "insider": "CHECKED_NO_EVENTS",
            "allowed_action": "MANUELL VURDERING" if action != "BUY" else "BUY",
        },
        "raw": {
            "technical": {"trend": "STIGENDE", "rsi": 49.123456},
            "fundamental": {"roe": 19.153000000000002},
            "news_score": 50,
            "news_intelligence": {"coverage": "CHECKED_NO_EVENTS", "events": [], "search_log": []},
            "insider_intelligence": {"coverage": "CHECKED_NO_EVENTS", "evidence": [], "search_log": []},
            "score_formula": {"parts": {}, "weights": {}, "weighted_contributions": {}},
        },
    }


def run(rows: list[dict]) -> dict:
    actions = {"BUY": 0, "REVIEW": 0, "SKIP": 0}
    for row in rows:
        actions[row["portfolio_action"]] = actions.get(row["portfolio_action"], 0) + 1
    return {
        "run_id": "MI-19132-TEST",
        "created_at": "2026-07-28T08:57:20+02:00",
        "timezone_name": "Europe/Oslo",
        "job_id": "TEST",
        "job_name": "Morgenrapport",
        "trigger": "MANUAL_DRAFT_TEST",
        "markets": ["USA"],
        "summary": {"scanned": len(rows), "deep_analyzed": len(rows), "proposals": 2, "recommended": 0},
        "candidates": rows,
        "proposals": [dict(rows[0]), dict(rows[-1])],
        "portfolio_decisions": {"production_threshold": 78, "actions": actions},
        "data_quality": {"score": 100, "label": "UTMERKET", "errors": 0},
        "combined_data_quality": {"evaluated": len(rows), "overall_valid": sum(bool(x["evidence_valid_for_decision"]) for x in rows)},
        "market_diagnostics": [{
            "market": "Finland", "scanned": 10, "analyzed": 9, "live": 9,
            "errors": 2,
            "candidate_errors": [
                {"ticker": "LEHTO.HE", "stage": "prepare", "error": "bad number"},
                {"ticker": "LEHTO.HE", "stage": "score", "error": "bad number"},
            ],
        }],
        "autonomous_chain": {"stages": [{"name": "AUTONOMOUS_PORTFOLIO", "detail": {
            "ordinary_buys": 0, "buys": 3, "learning_buys": 3,
            "open_positions": 12, "learning_open_positions": 15,
            "learning_buy_tickers": ["AAA", "BBB", "CCC"],
        }}]},
        "report_status": {"state": "PROVISIONAL", "label": "FORELØPIG"},
        "report_revision": {"revision": 1, "revision_label": "R1"},
        "errors": [], "warnings": [], "changes": {},
    }


def pdf_text(payload: dict) -> str:
    pdf = mi.build_pdf(payload)
    return "\n".join(page.extract_text() or "" for page in PdfReader(BytesIO(pdf)).pages)


def test_review_candidates_are_evidence_ready_but_not_final_decision_ready():
    result = canonical_report_view(run([candidate("MO", 76.3), candidate("CASY", 75.1)]))
    assert result["report_summary"]["evidence_data_ready"] == 2
    assert result["report_summary"]["decision_ready"] == 0
    assert result["top3_status"]["display_mode"] == "EVIDENCE_SHORTLIST"
    assert [x["ticker"] for x in result["evidence_ready_top3"]] == ["MO", "CASY"]
    assert result["decision_ready_top3"] == []


def test_pdf_has_no_medals_for_review_shortlist_and_uses_full_status_and_formatted_numbers():
    text = pdf_text(run([candidate("MO", 76.3), candidate("CASY", 75.1)]))
    assert "Evidens- og dataklar kortliste (2 kandidat(er))" in text
    assert "EVIDENSKORTLISTE · PLASS 1" in text
    assert all(word not in text for word in ("GULL", "SØLV", "BRONSE"))
    assert "KREVER MANUELL VURDERING –\nDOKUMENTASJON" in text or "KREVER MANUELL VURDERING – DOKUMENTASJON" in text
    assert "19.153000000000002" not in text
    assert "19.153" in text
    assert "Scoretrend" in text


def test_diagnostics_count_unique_skipped_candidates_not_error_events():
    result = canonical_report_view(run([candidate("MO", 76.3)]))
    diag = result["market_diagnostics"][0]
    assert diag["skipped_candidate_count"] == 1
    assert diag["candidate_error_events"] == 2
    assert diag["errors"] == 0
    assert result["diagnostics_summary"]["skipped_candidate_count"] == 1


def test_learning_activity_is_separate_and_zero_production_is_not_replaced_by_total_buys():
    result = canonical_report_view(run([candidate("MO", 76.3)]))
    summary = result["learning_portfolio_summary"]
    assert summary["production_buys"] == 0
    assert summary["learning_buys"] == 3
    text = pdf_text(result)
    assert "0 produksjonskjøp / 3 læringskjøp" in text


def test_proposals_are_explicitly_preliminary_not_trade_proposals():
    result = canonical_report_view(run([candidate("MO", 76.3), candidate("CASY", 75.1)]))
    assert result["proposal_summary"]["preliminary_model_candidates"] == 2
    assert result["proposal_summary"]["final_buy_candidates"] == 0
    assert all(row["proposal_stage"] == "PRELIMINARY_MODEL_OUTPUT" for row in result["proposals"])
    text = pdf_text(result)
    assert "Foreløpige modellkandidater" in text
    assert "ikke handelsforslag" in text


def test_reanalysis_flattens_prior_assessment_wrappers():
    source = {"ticker": "MO", "market": "USA", "price": 50.0}
    previous = {"ticker": "MO", "market": "USA", "candidate_id": "MO:USA", "investment_score": 70, "raw": source}
    current = {"ticker": "MO", "market": "USA", "candidate_id": "MO:USA", "investment_score": 75, "raw": previous}
    flattened = _source_row_for_reanalysis(current)
    assert flattened["price"] == 50.0
    assert "raw" not in flattened
    assert flattened["analysis_wrapper_depth_removed"] == 2
    assert flattened["previous_analysis_snapshot"]["authoritative"] is False


def test_mobile_pdf_is_download_first_and_public_link_opens_new_tab():
    source = Path(mi.__file__).read_text()
    assert "Last ned PDF – behold appen åpen" in source
    assert 'target="_blank"' in source
    assert "På mobil: bruk nedlastingsknappen" in source
    assert "Åpne / last ned PDF-rapport" not in source


def test_external_article_titles_remain_verbatim_while_internal_codes_are_localized():
    row = candidate("MO", 76.3)
    row["raw"]["news_intelligence"] = {
        "coverage": "AVAILABLE",
        "events": [{
            "title": "Altria Stock: Why Q2 Matters for Its High-Yield Earnings",
            "published_at": "2026-07-28T00:55:00+00:00",
            "source": "Example News",
            "topics": ["EARNINGS"],
            "sentiment_score": 0.8,
            "impact": "HIGH",
            "verification": "VERIFIED",
        }],
        "search_log": [],
    }
    row["raw"]["insider_intelligence"] = {
        "coverage": "AVAILABLE",
        "evidence": [{
            "insider": "EXAMPLE PERSON",
            "role": "Director",
            "type": "BUY",
            "date": "2026-07-28",
            "shares": 10,
            "value": 1000,
            "verification": "VERIFIED",
            "source": "STRUCTURED_PROVIDER",
        }],
        "search_log": [],
    }
    text = pdf_text(run([row]))
    assert "High-Yield\nEarnings" in text or "High-Yield Earnings" in text
    assert "Høy-Yield" not in text
    assert "KJØP" in text
    assert "Direktør" in text
    assert "Høy" in text
    assert "STRUKTURERT_PROVIDER" not in text
