from investment_pipeline import _merge_candidate_rows, infer_market_from_ticker
from market_intelligence import build_pdf


def test_market_identity_and_global_source_filtering():
    assert infer_market_from_ticker("EQNR.OL") == "Norge"
    assert infer_market_from_ticker("VOLV-B.ST") == "Sverige"
    assert infer_market_from_ticker("NESTE.HE") == "Finland"
    assert infer_market_from_ticker("NOVO-B.CO") == "Danmark"
    assert infer_market_from_ticker("PETR4.SA") == "Brasil"
    assert infer_market_from_ticker("MMM") == "USA"
    rows = _merge_candidate_rows(
        [{"ticker": "NESTE.HE", "market": "Brasil"}, {"ticker": "VOLV-B.ST"}],
        [{"ticker": "NOKIA.HE"}, {"ticker": "NESTE.HE"}],
        "Finland",
        25,
    )
    assert [row["ticker"] for row in rows] == ["NESTE.HE", "NOKIA.HE"]
    assert all(row["market"] == "Finland" for row in rows)


def test_aborted_report_contains_no_false_ranking():
    pdf = build_pdf({
        "run_id": "TEST", "created_at": "2026-07-19T00:00:00+00:00", "markets": ["Norge"],
        "summary": {"scanned": 1, "deep_analyzed": 1, "proposals": 0, "recommended": 0},
        "analysis_aborted": True,
        "candidates": [{"ticker": "EQNR.OL", "market": "Norge", "investment_score": 51.0}],
        "proposals": [], "changes": {}, "data_refresh": {}, "market_status": [], "data_quality": {},
        "portfolio_proposal": {"allocations": []},
    })
    assert pdf.startswith(b"%PDF")
