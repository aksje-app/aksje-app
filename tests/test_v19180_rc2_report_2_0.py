from io import BytesIO
from pypdf import PdfReader
import market_intelligence as mi
from app_version import APP_VERSION


def _text(pdf: bytes) -> str:
    return "\n".join((p.extract_text() or "") for p in PdfReader(BytesIO(pdf)).pages)


def test_report_2_0_front_page_and_traceability():
    run = {
        "run_id": "MI-REPORT20-TEST",
        "analysis_id": "AN-REPORT20-TEST",
        "created_at": "2026-08-04T08:00:00+00:00",
        "timezone_name": "Europe/Oslo",
        "job_id": "JOB-MORNING",
        "job_name": "Morgenanalyse",
        "trigger": "SCHEDULED",
        "markets": ["Norge", "Sverige", "USA"],
        "summary": {"scanned": 1, "deep_analyzed": 1, "recommended": 1},
        "data_quality": {"score": 92},
        "candidates": [{
            "ticker": "EQNR.OL",
            "rank": 1,
            "investment_score": 84.25,
            "final_score": 84.25,
            "portfolio_action": "REVIEW",
            "decision": "REVIEW",
            "price": 300.0,
            "data_quality_score": 92,
            "risk_score": 35,
            "raw": {},
        }],
    }
    before = [(r.get('ticker'), r.get('investment_score'), r.get('portfolio_action')) for r in run.get('candidates', [])]
    text = _text(mi.build_pdf(run))
    after = [(r.get('ticker'), r.get('investment_score'), r.get('portfolio_action')) for r in run.get('candidates', [])]
    assert APP_VERSION.startswith("v19.22.0-rc")
    assert before == after
    for needle in (
        'Hovedkonklusjon', 'Top 1-3 - investeringsrangering',
        'Markedsdatakvalitet', 'Teknisk dokumentasjon', 'Kandidatenes evidens', 'Uavhengige kilder',
        'Beslutningsstyrke', 'Analyse-ID', 'Sporbarhet: program',
    ):
        assert needle in text
    assert text.index('Top 1-3 - investeringsrangering') < text.index('Endringer siden forrige rapport')
    assert 'Pålitelighet\n49/100' not in text
