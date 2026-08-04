from io import BytesIO
from pypdf import PdfReader
import market_intelligence as mi


def _text(run):
    return "\n".join(page.extract_text() or "" for page in PdfReader(BytesIO(mi.build_pdf(run))).pages)


def test_evening_report_uses_evening_mission_and_norwegian_actions():
    run = {
        "run_id": "MI-1912-EVENING",
        "created_at": "2026-07-23T20:30:00+00:00",
        "timezone_name": "Europe/Oslo",
        "job_id": "JOB-1", "job_name": "Morgenanalyse", "trigger": "SCHEDULED",
        "markets": ["USA"],
        "summary": {"scanned": 1, "deep_analyzed": 1, "recommended": 1},
        "portfolio_decisions": {"actions": {"BUY": 0, "REVIEW": 1, "SKIP": 0}},
        "user_mission": {"objective": "Morgenanalyse", "search_for": "Morgenanalyse", "horizon": "1-3 mnd", "risk": "Balansert"},
        "candidates": [], "data_quality": {"score": 80},
    }
    text = _text(run)
    assert "Kveldsrapport – Markedsanalyse" in text
    assert "Kveldsanalyse" in text
    assert "Kandidater til neste handelsdag" in text
    assert "REVIEW" not in text
    assert "Executive Summary" in text


def test_source_log_uses_short_date_and_localized_status():
    run = {
        "run_id": "MI-1912-SOURCE",
        "created_at": "2026-07-23T20:30:00+00:00",
        "timezone_name": "Europe/Oslo",
        "job_id": "JOB-2", "job_name": "Kveldsanalyse", "trigger": "SCHEDULED",
        "markets": ["USA"], "summary": {},
        "candidates": [{
            "ticker": "TEST", "rank": 1, "investment_score": 70, "portfolio_action": "REVIEW",
            "raw": {"insider_intelligence": {"coverage": "NOT_SEARCHED", "search_log": [{
                "source": "Simply Wall St.", "attempted": True, "status": "NOT_SEARCHED",
                "checked_at": "2026-07-17T22:15:04+00:00", "results": 0,
            }]}, "news_intelligence": {"coverage": "NOT_SEARCHED", "search_log": []}},
        }],
    }
    text = _text(run)
    assert "17.07.2026 22:15" in text
    assert "Ikke søkt" in text
    assert "2026-07-17T22:15:04+00:00" not in text
