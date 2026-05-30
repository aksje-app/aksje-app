from pathlib import Path

from ranking_universe_adapters import (
    attach_shared_ranking_to_smart_result,
    build_shared_top_picks,
    enrich_existing_ranking_rows,
    existing_rows_to_ranking_rows,
    rank_existing_rows,
)


def test_existing_rows_normalize_score_scales_without_fetching():
    rows = existing_rows_to_ranking_rows(
        [
            {"ticker": "kog.ol", "name": "Kongsberg Gruppen", "score": 8.2, "source": "Marked/rangering"},
            {"ticker": "nas.ol", "name": "Norwegian Air Shuttle", "smart_score": 71, "source": "Smart AI"},
        ],
        source="Marked/rangering",
    )

    assert rows[0]["ticker"] == "kog.ol"
    assert rows[0]["score"] == 82.0
    assert rows[1]["score"] == 71.0
    assert rows[0]["ranking_adapter_version"].startswith("v18.6.3")


def test_rank_existing_rows_dedupes_cached_top_picks_and_market_rows():
    result = rank_existing_rows(
        [
            {"ticker": "KOG.OL", "name": "Kongsberg Gruppen", "score": 8.4, "source": "Top Picks"},
            {"ticker": "KOG.OL", "name": "Kongsberg Gruppen", "score": 7.6, "source": "Norge"},
            {"ticker": "ELK.OL", "name": "Elkem", "score": 7.9, "source": "Norge"},
        ],
        source="Felles test",
        request={"max_count": 10},
    )

    tickers = [row.candidate.ticker for row in result.ranked]
    assert tickers.count("KOG.OL") == 1
    assert set(tickers) == {"KOG.OL", "ELK.OL"}
    kog = next(row.as_dict() for row in result.ranked if row.candidate.ticker == "KOG.OL")
    assert "Felles test" in kog["source"]
    assert kog["candidate"]["metadata"]["merged_count"] == 2


def test_build_shared_top_picks_preserves_legacy_shape_and_adds_shared_fields():
    rows = [
        {"ticker": "AAA.OL", "name": "AAA", "score": 8.7, "risk_score": 20},
        {"ticker": "BBB.OL", "name": "BBB", "score": 7.1, "risk_score": 45},
        {"ticker": "CCC.OL", "name": "CCC", "score": 5.9, "risk_score": 10},
    ]

    picks = build_shared_top_picks(rows, min_score=6.5, max_items=5)

    assert [row["ticker"] for row in picks] == ["AAA.OL", "BBB.OL"]
    assert picks[0]["score"] == 8.7
    assert picks[0]["shared_rank"] == 1
    assert picks[0]["shared_score"] is not None
    assert picks[0]["shared_score_components"]
    assert "shared_ranking_version" in picks[0]


def test_enrich_existing_rows_does_not_drop_app_fields():
    enriched = enrich_existing_ranking_rows(
        [
            {
                "ticker": "DNB.OL",
                "name": "DNB Bank",
                "score": 7.8,
                "custom_ui_field": "behold denne",
                "evidence_items": [{"type": "Nyhet", "title": "Kapitalmarkedsdag"}],
            }
        ],
        source="Marked/rangering",
    )

    assert enriched[0]["custom_ui_field"] == "behold denne"
    assert enriched[0]["shared_evidence_summary"]["totalt"] == 1


def test_smart_result_gets_shared_ranking_without_changing_scan_counts():
    result = {
        "scanned": 2,
        "raw_candidates": 2,
        "matched_candidates": 2,
        "candidates": [
            {"ticker": "AAA.OL", "name": "AAA", "ai_score": 8.0, "smart_score": 77, "strength": 70},
            {"ticker": "BBB.OL", "name": "BBB", "ai_score": 7.5, "smart_score": 74, "strength": 60},
        ],
        "top_picks": [{"ticker": "AAA.OL"}, {"ticker": "BBB.OL"}],
    }

    attached = attach_shared_ranking_to_smart_result(result)

    assert attached["scanned"] == 2
    assert attached["shared_ranking"]["status"] == "ok"
    assert attached["candidates"][0]["shared_rank"] == 1
    assert attached["top_tickers"][0] == "AAA.OL"


def test_universe_adapter_stays_pure_and_lightweight():
    source = Path("ranking_universe_adapters.py").read_text(encoding="utf-8")
    lowered = source.lower()
    for forbidden in ("streamlit", "requests", "yfinance", "score_stock", "auto_rank_market", "rank_stocks"):
        assert forbidden not in lowered



