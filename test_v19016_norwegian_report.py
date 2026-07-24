from __future__ import annotations

import io
from pypdf import PdfReader

from market_intelligence import build_pdf, build_text_report
from norwegian_report_language import translate_report_text, decision_label, sector_label, model_role_label, USER_FACING_ENGLISH_BLOCKLIST


def _sample_run():
    candidate = {
        "rank": 1,
        "ticker": "CHRW",
        "name": "C.H. Robinson",
        "market": "USA",
        "sector": "Industrials",
        "status": "ANBEFALT FOR VURDERING",
        "portfolio_action": "REVIEW",
        "investment_score": 74.28,
        "confidence_score": 91.11,
        "risk_score": 33.4,
        "discovery_score": 86.92,
        "fundamental_score": 61.35,
        "research_score": 60.97,
        "validation_score": 94.84,
        "portfolio_fit_score": 66.63,
        "trend": "NY",
        "strategy_matches": ["Growth", "Momentum", "Value", "Income", "Quality", "Event Recovery"],
        "raw": {
            "insider_score": 77.12,
            "news_score": 80.0,
            "insider_signal": "NEUTRAL",
            "news_sentiment": "POSITIVE",
            "insider_intelligence": {"coverage": "AVAILABLE", "buy_count": 1, "sell_count": 0, "net_value": 10000, "currency": "USD", "search_log": []},
            "news_intelligence": {"coverage": "AVAILABLE", "summary": "Backtesting and Research improved confidence", "search_log": []},
            "discovery_evidence": "AI Discovery found Growth and Quality signals",
            "backtest": "Backtesting is strong",
        },
        "decision_readiness": {"status": "VERIFIED", "market_data": "VERIFIED", "news": "VERIFIED_FACTS_FOUND", "insider": "VERIFIED_FACTS_FOUND", "conflicts": 0, "allowed_action": "REVIEW"},
        "confidence_profile": {"model_confidence": 92, "data_coverage": 90, "calibrated_confidence": 91, "decision_confidence": 88, "explanation": "Confidence based on backtesting"},
        "analysis_ranking": {"sector": "Industrials", "matches": ["Growth", "Event Recovery"]},
        "evidence_passport": {"fingerprint": "abc", "areas": {"news": {"status": "VERIFIED", "fact_count": 2, "source_count": 1, "affected_ranking": True, "ranking_contribution": 1.2}}},
        "positives": ["Growth", "Backtesting"],
        "risks": ["Review required"],
    }
    return {
        "run_id": "MI-TEST-V19016",
        "job_name": "Morgenanalyse",
        "created_at": "2026-07-24T08:30:00+00:00",
        "timezone_name": "Europe/Oslo",
        "markets": ["USA"],
        "summary": {"scanned": 10, "deep_analyzed": 1, "proposals": 1, "recommended": 1},
        "data_quality": {"score": 91, "label": "HIGH", "live": 10, "cache": 0, "errors": 0},
        "combined_quality": {"evaluated": 1, "overall_valid": 1, "manual_review_required": 1},
        "notification": {"status": "SENT", "status_label": "Pushover sent"},
        "report_status": {"state": "PROVISIONAL", "critical_gaps": [{"ticker": "CHRW", "area": "insider", "status": "VERIFIED"}]},
        "portfolio_decisions": {"actions": {"BUY": 0, "REVIEW": 1, "SKIP": 0}, "portfolio_context": {}, "approval_rule": "BUY requires portfolio review"},
        "decision_funnel": {"evaluated": 1, "eligible": 0, "rejected": 1, "production_threshold": 73, "near_threshold": [{"ticker": "CHRW", "score": 74.28, "production_threshold": 73, "data_quality": 91, "risk": 33, "portfolio_action": "REVIEW", "reasons": ["Model gave REVIEW"]}], "shadow_thresholds": [{"threshold": 74, "role": "CHALLENGER", "score_qualified_count": 1, "eligible_count": 0, "eligible_tickers": ["CHRW"]}], "position_provenance": [{"ticker": "CHRW", "origin": "AUTONOMY_THRESHOLD", "source_run_id": "X", "evidence": "VERIFIED"}]},
        "candidates": [candidate],
        "proposals": [candidate],
    }


def test_translation_helpers():
    assert decision_label("REVIEW") == "Krever manuell vurdering"
    assert sector_label("Industrials") == "Industri"
    assert model_role_label("CHALLENGER") == "Utfordrer"
    assert "Historisk test" in translate_report_text("Backtesting")


def test_text_report_uses_norwegian_decisions():
    text = build_text_report(_sample_run())
    assert "Krever manuell vurdering" in text
    assert "REVIEW" not in text


def test_pdf_report_localizes_user_facing_terms():
    pdf_bytes = build_pdf(_sample_run())
    reader = PdfReader(io.BytesIO(pdf_bytes))
    text = "\n".join(page.extract_text() or "" for page in reader.pages)
    required = ["KREVER MANUELL VURDERING", "VERIFISERT", "Utfordrer", "Historisk test", "AI-funn", "Industri", "Vekst"]
    for word in required:
        assert word in text, word
    forbidden = ["Portfolio & Decision Layer", "Shadow Mode", "Backtesting", "AI Discovery", "CHALLENGER", "PRODUCTION", "VERIFIED"]
    for word in forbidden:
        assert word not in text, word


if __name__ == "__main__":
    test_translation_helpers()
    test_text_report_uses_norwegian_decisions()
    test_pdf_report_localizes_user_facing_terms()
    print("v19.0.16 localization tests passed")
