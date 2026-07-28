from __future__ import annotations

from io import BytesIO

from pypdf import PdfReader

import market_intelligence as mi
from decision_report import candidate_source_consensus
from report_contracts import ensure_report_document, section_payload
from report_integrity import canonical_report_view, validate_report_integrity


def _candidate(
    ticker: str,
    score: float,
    *,
    trend: str = "STABIL",
    raw_trend: str | None = None,
    action: str = "REVIEW",
    insider_status: str = "NOT_SEARCHED",
    news_status: str = "NOT_SEARCHED",
    news_events: list[dict] | None = None,
    insider_attempted: bool = False,
) -> dict:
    insider_log = []
    if insider_attempted:
        insider_log = [{
            "source": "NewsAPI-kildeoppdagelse",
            "source_type": "SECONDARY_SOURCE_DISCOVERY",
            "attempted": True,
            "status": "SOURCE_ERROR",
            "results": 0,
        }]
    return {
        "ticker": ticker,
        "name": ticker,
        "market": "Norge",
        "rank": 1,
        "raw_rank": 1,
        "investment_score": score,
        "confidence_score": 60,
        "risk_score": 30,
        "trend": trend,
        "status": "KREVER MANUELL VURDERING",
        "portfolio_action": action,
        "valid_for_decision": True,
        "evidence_valid_for_decision": False,
        "decision_readiness": {
            "status": "IKKE KOMPLETT",
            "market_data": "GYLDIG",
            "insider": insider_status,
            "news": news_status,
            "allowed_action": "MANUELL VURDERING",
            "confidence_final": 60,
            "conflicts": 0,
        },
        "raw": {
            "trend": raw_trend if raw_trend is not None else trend,
            "technical": {"trend": raw_trend if raw_trend is not None else trend},
            "score_formula": {
                "investment_score": score,
                "parts": {"insider": 50, "news": 50},
                "weights": {"insider": 0.069, "news": 0.0862},
                "weighted_contributions": {"insider": 3.45, "news": 4.31},
            },
            "insider_intelligence": {
                "coverage": insider_status,
                "official_source": "Oslo Børs NewsWeb / Finanstilsynet",
                "evidence": [],
                "search_log": insider_log,
            },
            "news_intelligence": {
                "coverage": news_status,
                "events": list(news_events or []),
                "search_log": [{
                    "source": "yfinance company news",
                    "source_type": "SECONDARY_AGGREGATOR",
                    "attempted": bool(news_events),
                    "status": "SUCCESS_WITH_RESULTS" if news_events else "NOT_ATTEMPTED",
                    "results": len(news_events or []),
                }],
            },
        },
    }


def _run(candidates: list[dict]) -> dict:
    return {
        "run_id": "MI-19131-TEST",
        "created_at": "2026-07-27T18:47:48+00:00",
        "timezone_name": "Europe/Oslo",
        "job_id": "MI-DRAFT-AUTOSAVE",
        "job_name": "Kveldsrapport",
        "trigger": "MANUAL_DRAFT_TEST",
        "markets": ["Norge"],
        "summary": {"scanned": 24, "deep_analyzed": 0, "proposals": 0, "recommended": 0},
        "executive_intelligence": {
            "average_score": 0.0,
            "highest_score": 0.0,
            "lowest_score": 0.0,
            "unique_companies": 0,
            "markets_in_top10": 0,
        },
        "candidates": candidates,
        "portfolio_decisions": {
            "production_threshold": 73,
            "actions": {"BUY": 0, "REVIEW": sum(c["portfolio_action"] == "REVIEW" for c in candidates), "SKIP": sum(c["portfolio_action"] == "SKIP" for c in candidates)},
        },
        "data_quality": {"score": 100, "label": "UTMERKET"},
        "combined_data_quality": {"evaluated": len(candidates), "overall_valid": 0},
        "report_status": {"state": "PROVISIONAL", "label": "FORELØPIG"},
        "report_revision": {"revision": 2, "revision_label": "R2"},
        "errors": [],
        "warnings": [],
        "changes": {},
    }


def test_canonical_view_recomputes_stale_summary_and_keeps_score_trend_separate_from_technical_trend():
    run = _run([
        _candidate("STB.OL", 77.06),
        _candidate("WWI.OL", 72.86, action="SKIP"),
        _candidate("FRO.OL", 66.50, trend="FALLENDE", raw_trend="STIGENDE"),
    ])
    result = canonical_report_view(run)

    assert result["executive_intelligence"] == {
        "average_score": 72.14,
        "highest_score": 77.06,
        "lowest_score": 66.5,
        "unique_companies": 3,
        "markets_in_top10": 1,
    }
    assert result["report_summary"]["manual_review"] == 2
    fro = result["candidates"][2]
    assert fro["score_trend"] == "FALLENDE"
    assert fro["trend_basis"] == "Kandidatscore sammenlignet med forrige analysekjøring"
    assert fro["raw"]["trend"] == "STIGENDE"
    assert fro["raw"]["technical"]["trend"] == "STIGENDE"
    assert validate_report_integrity(result)["ok"] is True


def test_unverified_positive_components_are_explicit_model_baselines():
    result = canonical_report_view(_run([_candidate("FRO.OL", 66.5)]))
    semantics = result["candidates"][0]["raw"]["score_formula"]["contribution_semantics"]

    assert semantics["insider"]["evidence_backed"] is False
    assert semantics["news"]["evidence_backed"] is False
    assert "modellbaseline" in semantics["insider"]["display_label"].casefold()
    assert semantics["insider"]["contribution"] == 3.45


def test_evidence_gate_and_final_portfolio_action_remain_separate():
    result = canonical_report_view(_run([_candidate("WWI.OL", 72.86, action="SKIP")]))
    readiness = result["candidates"][0]["decision_readiness"]

    assert readiness["evidence_gate_action"] == "MANUELL VURDERING"
    assert readiness["final_action"] == "SKIP"
    assert result["candidates"][0]["portfolio_action"] == "SKIP"


def test_source_consensus_deduplicates_aggregator_and_same_publisher_chain():
    events = [
        {
            "title": "Article one",
            "publisher": "Simply Wall St.",
            "original_publisher": "Simply Wall St.",
            "collector_source": "Yahoo Finance / yfinance",
            "source_type": "PUBLISHED_NEWS",
        },
        {
            "title": "Article two",
            "publisher": "Simply Wall St.",
            "original_publisher": "Simply Wall St.",
            "collector_source": "Yahoo Finance / yfinance",
            "source_type": "PUBLISHED_NEWS",
        },
    ]
    candidate = _candidate(
        "WWI.OL", 72.86,
        news_status="VERIFIED_FACTS_FOUND",
        insider_status="PARTIAL_SOURCE_FAILURE",
        news_events=events,
        insider_attempted=True,
    )
    consensus = candidate_source_consensus(candidate)

    assert consensus["independent_sources"] == 1
    assert consensus["sources"] == ["Simply Wall St."]
    assert consensus["level"] == "SVAK"
    assert consensus["primary_source_present"] is False


def test_insider_coverage_distinguishes_source_errors_from_not_searched():
    candidates = [
        _candidate(f"ERR{i}.OL", 70 - i, insider_status="PARTIAL_SOURCE_FAILURE", insider_attempted=True)
        for i in range(5)
    ] + [
        _candidate(f"NEW{i}.OL", 65 - i, insider_status="NOT_SEARCHED")
        for i in range(5)
    ]
    coverage = mi.insider_coverage_by_market(candidates)[0]

    assert coverage["checked"] == 5
    assert coverage["verified"] == 0
    assert coverage["source_errors"] == 5
    assert coverage["not_searched"] == 5
    assert coverage["no_events"] == 0


def test_test_runs_are_silent_unless_test_notification_is_explicit():
    assert mi.should_suppress_notifications("MANUAL_DRAFT_TEST", True) is True
    assert mi.should_suppress_notifications("MANUAL_DRAFT_TEST", False) is True
    assert mi.should_suppress_notifications("MANUAL_DRAFT_TEST_NOTIFICATION", True) is False
    assert mi.should_suppress_notifications("SCHEDULED", True) is False
    assert mi.should_suppress_notifications("SCHEDULED", False) is True


def test_pdf_uses_raw_ranking_and_canonical_summary_when_none_are_decision_ready():
    run = _run([
        _candidate("STB.OL", 77.06, insider_status="PARTIAL_SOURCE_FAILURE", news_status="VERIFIED_FACTS_FOUND", insider_attempted=True, news_events=[{"publisher": "GuruFocus.com", "original_publisher": "GuruFocus.com", "title": "News"}]),
        _candidate("WWI.OL", 72.86, action="SKIP", insider_status="PARTIAL_SOURCE_FAILURE", news_status="VERIFIED_FACTS_FOUND", insider_attempted=True, news_events=[{"publisher": "Simply Wall St.", "original_publisher": "Simply Wall St.", "title": "News"}]),
        _candidate("FRO.OL", 66.5, trend="FALLENDE", raw_trend="STIGENDE"),
    ])
    pdf = mi.build_pdf(run)
    text = "\n".join(page.extract_text() or "" for page in PdfReader(BytesIO(pdf)).pages)

    assert "RÅ RANGERING · PLASS 1" in text
    assert "GULL - BESTE KANDIDAT" not in text
    assert "Til manuell vurdering" in text
    assert "72.14" in text
    assert "Evidensport" in text
    assert "Endelig beslutning" in text
    assert "modellbaseline" in text.casefold()


def test_report_document_carries_canonical_summary_and_integrity_status():
    canonical = canonical_report_view(_run([_candidate("FRO.OL", 66.5)]))
    document = ensure_report_document(canonical)
    executive = section_payload(document, "executive_summary", {})
    technical = section_payload(document, "technical_status", {})

    assert executive["report_summary"]["deep_analyzed"] == 1
    assert executive["executive_intelligence"]["highest_score"] == 66.5
    assert technical["report_integrity"]["ok"] is True
