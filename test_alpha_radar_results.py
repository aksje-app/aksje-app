import io
import zipfile

from alpha_radar_results import (
    alpha_radar_candidate_tickers,
    alpha_radar_result_to_active_universe_payload,
    alpha_radar_result_to_csv,
    alpha_radar_result_to_print_html,
    alpha_radar_result_to_ticker_text,
    alpha_radar_result_to_xlsx,
)


RESULT = {
    "created_at": "2026-05-22 21:30",
    "scope": "Norge",
    "horizon": "3m",
    "mode": "Blandet Alpha Radar",
    "precision_level": "Balansert",
    "candidates": [
        {
            "rank": 1,
            "ticker": "MICRO.OL",
            "name": "Real Micro",
            "market": "Norge",
            "hidden_potential_score": 72.4,
            "catalyst_score": None,
            "insider_score": 64.0,
            "macro_score": None,
            "factor_quality": {"catalyst": "mangler", "insider_bjellesau": "ekte"},
            "why_now": "Tidlig vendepunkt med lav dekning.",
            "signals": ["Borsverdi", "Resultater"],
            "reject_reasons": [],
            "warning_reasons": ["tynt volum"],
            "manual_review": "Manuell sjekk.",
            "evidence_items": [
                {
                    "type": "nyhet",
                    "title": "Kontrakt vunnet",
                    "source": "Borsmelding",
                    "published": "2026-05-22",
                    "detail": "Katalysator",
                    "url": "https://example.com/news",
                }
            ],
            "news_evidence": [
                {
                    "title": "Kontrakt vunnet",
                    "source": "Borsmelding",
                    "published": "2026-05-22",
                    "detail": "Katalysator",
                    "url": "https://example.com/news",
                }
            ],
            "insider_evidence": [],
        },
        {
            "rank": 2,
            "ticker": "HIDE.ST",
            "name": "Hidden Sweden",
            "market": "Sverige",
            "hidden_potential_score": 69.1,
            "why_now": "Katalysator i lite dekket case.",
            "signals": ["Nyheter/katalysator"],
            "reject_reasons": ["bekreft likviditet"],
            "warning_reasons": [],
            "manual_review": "Manuell sjekk.",
        },
    ],
}


def test_alpha_radar_exports_csv_html_and_ticker_text():
    csv_bytes = alpha_radar_result_to_csv(RESULT)
    html_bytes = alpha_radar_result_to_print_html(RESULT)
    tickers = alpha_radar_result_to_ticker_text(RESULT)
    xlsx_bytes = alpha_radar_result_to_xlsx(RESULT)

    assert b"MICRO.OL" in csv_bytes
    assert b"HIDE.ST" in csv_bytes
    assert b"window.print" in html_bytes
    assert b"Datakvalitet" in html_bytes
    assert b"https://example.com/news" in html_bytes
    assert b"evidence_summary" in csv_bytes
    assert xlsx_bytes[:2] == b"PK"
    with zipfile.ZipFile(io.BytesIO(xlsx_bytes)) as zf:
        assert "xl/workbook.xml" in zf.namelist()
        assert "xl/worksheets/sheet2.xml" in zf.namelist()
        assert "xl/worksheets/sheet5.xml" in zf.namelist()
    assert tickers.decode("utf-8").splitlines() == ["MICRO.OL", "HIDE.ST"]


def test_alpha_radar_result_can_become_active_universe_payload():
    payload = alpha_radar_result_to_active_universe_payload(RESULT)

    assert alpha_radar_candidate_tickers(RESULT) == ["MICRO.OL", "HIDE.ST"]
    assert payload["source"] == "Alpha Radar"
    assert payload["tickers"] == ["MICRO.OL", "HIDE.ST"]
    assert payload["rows"][0]["status"] == "Alpha Radar hypotese"








