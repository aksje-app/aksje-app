from io import BytesIO

from pypdf import PdfReader

import market_intelligence as mi


def _candidate(index: int) -> dict:
    raw = {
        "insider_score": 82.0,
        "insider_signal": "POSITIV",
        "insider_intelligence": {
            "coverage": "AVAILABLE", "buy_count": 5, "sell_count": 1,
            "net_value": 125000,
        },
        "news_score": 80.0,
        "news_sentiment": "POSITIV",
        "news_intelligence": {
            "coverage": "AVAILABLE", "article_count": 3,
            "high_impact_count": 1,
            "summary": "Positivt nyhetsbilde med relevant selskapsinformasjon.",
        },
    }
    return {
        "rank": index, "ticker": f"TEST{index}.OL", "name": f"Test {index}",
        "market": "Norge", "investment_score": 76.0-index/10,
        "confidence_score": 91.0, "trend": "STABIL", "risk_score": 14.0,
        "status": "ANBEFALT FOR VURDERING", "discovery_score": 70.0,
        "fundamental_score": 88.0, "research_score": 57.0,
        "validation_score": 90.0, "portfolio_fit_score": 71.0,
        "proposed_position_pct": 4.2, "raw": raw,
    }


def _representative_run() -> dict:
    candidates = [_candidate(i) for i in range(1, 31)]
    proposals = [
        {**row, "positives": ["Fundamentaler trekker opp.", "Backtesting trekker opp."],
         "risks": ["Manuell kontroll kreves."], "strategy_match": "Momentum"}
        for row in candidates[:8]
    ]
    trace = [
        {"ticker": row["ticker"], "market": "Norge", "data_source": "yfinance-live",
         "data_fetch_status": "OK", "cache_bypass_applied": True,
         "latest_trade_date": "2026-07-20", "market_data_changed": True}
        for row in candidates
    ]
    return {
        "run_id": "MI-COMPACT-TEST", "created_at": "2026-07-20T09:11:04+00:00",
        "job_name": "Morgenanalyse", "trigger": "SCHEDULED",
        "markets": ["USA", "Norge", "Sverige", "Finland", "Danmark", "Brasil"],
        "summary": {"scanned": 147, "deep_analyzed": 120, "proposals": 30, "recommended": 7},
        "candidates": candidates, "proposals": proposals,
        "changes": {"new": [1, 2], "improved": [1] * 31, "weakened": [1], "dropped": [1, 2]},
        "market_diagnostics": [{"market": m, "scanned": 25, "analyzed": 20, "live": 20, "errors": 0, "status": "OK"} for m in ["USA", "Norge", "Sverige", "Finland", "Danmark", "Brasil"]],
        "data_quality": {"score": 100, "label": "HØY", "live": 120, "cache": 0, "errors": 0},
        "data_refresh": {"force_refresh_requested": True, "cache_bypass_verified": True,
                         "live_attempt_count": 120, "live_count": 120, "cache_count": 0,
                         "error_count": 0, "execution_trace": trace},
    }


def test_compact_pdf_is_readable_and_bounded():
    pdf = mi.build_pdf(_representative_run())
    reader = PdfReader(BytesIO(pdf))
    text = "\n".join(page.extract_text() or "" for page in reader.pages)
    assert pdf.startswith(b"%PDF")
    assert len(reader.pages) <= 6
    assert "Executive Summary" in text
    assert "TEST1.OL" in text
    assert "Metode og ansvarsfraskrivelse" in text
    assert "Side 1" in text


def test_compact_pdf_keeps_minimal_report_on_one_page():
    run = {"run_id": "MI-MIN", "created_at": "2026-07-20T09:11:04+00:00",
           "job_name": "Morgenanalyse", "trigger": "SCHEDULED", "markets": ["Norge"],
           "summary": {}, "candidates": [], "changes": {}, "data_refresh": {}}
    reader = PdfReader(BytesIO(mi.build_pdf(run)))
    assert len(reader.pages) == 1


def test_draft_job_id_overrides_stale_morning_report_identity():
    run = {
        "run_id": "MI-DRAFT-GUARD", "created_at": "2026-07-20T09:42:59+00:00",
        "job_id": mi.DRAFT_JOB_ID, "job_name": "Morgenanalyse",
        "trigger": "MANUAL_FULL_CHAIN",
        "report_identity": {"type": "MORGENRAPPORT", "label": "Morgenrapport", "slug": "Morgenrapport"},
        "markets": ["Norge"], "summary": {}, "candidates": [], "changes": {},
        "data_refresh": {},
    }
    identity = mi.resolve_report_identity(run)
    filename = mi.safe_report_filename(run)
    reader = PdfReader(BytesIO(mi.build_pdf(run)))
    text = "\n".join(page.extract_text() or "" for page in reader.pages)
    archive = mi._archive_entry(run)

    assert identity == {"type": "UTKAST", "label": "Utkast", "slug": "UTKAST"}
    assert filename.startswith("UTKAST_Morgenanalyse_")
    assert "Utkast – Market Intelligence" in text
    assert "UTKAST" in text
    assert archive["report_type"] == "UTKAST"
    assert archive["report_label"] == "Utkast"


def test_normal_morning_report_identity_is_unchanged():
    run = {"job_id": "MIJ-PRODUCTION", "job_name": "Morgenanalyse", "trigger": "MANUAL_FULL_CHAIN"}
    assert mi.resolve_report_identity(run)["type"] == "MORGENRAPPORT"
