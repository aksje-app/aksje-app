from ranking_evidence_adapters import (
    radar_result_to_ranking_rows,
    radar_results_to_ranking_result,
    rank_local_evidence_sources,
)


def test_alpha_radar_result_maps_to_shared_ranking_evidence_without_engine_run():
    result = {
        "analysis_engine": "Alpha Radar V2",
        "mode": "Blandet Alpha Radar",
        "scope": "Norge",
        "horizon": "3m",
        "precision_level": "Streng",
        "created_at": "2026-05-25T12:00:00",
        "candidates": [
            {
                "rank": 1,
                "ticker": "abc.ol",
                "name": "ABC ASA",
                "market": "Norge",
                "hidden_potential_score": 78,
                "alpha_score": 74,
                "catalyst_score": 67,
                "insider_score": 82,
                "risk_score": 31,
                "why_now": "Primarinnsider kjoper og kontrakt bekreftet.",
                "signals": ["Insider", "Nyhet/katalysator"],
                "insider_evidence": [
                    {
                        "type": "Insider",
                        "title": "Primarinnsider kjop",
                        "source": "NewsWeb",
                        "date": "2026-05-20",
                        "actor": "Kari CEO",
                        "actor_roles": ["Insider watch"],
                        "url": "https://example.test/newsweb",
                    }
                ],
            }
        ],
    }

    rows = radar_result_to_ranking_rows(result)
    ranked = radar_results_to_ranking_result(result)
    row = rows[0]
    top = ranked.ranked[0]

    assert row["source"] == "Alpha Radar"
    assert row["decision_source"] == "Alpha Radar"
    assert row["ticker"] == "ABC.OL"
    assert row["score"] == 78
    assert row["source_scope"] == "Norge"
    assert row["source_horizon"] == "3m"
    assert row["source_precision"] == "Streng"
    assert row["evidence_ledger"]
    assert top.candidate.source == "Alpha Radar"
    assert top.candidate.evidence_items[0].actor == "Kari CEO"
    assert top.evidence_summary["totalt"] >= 1


def test_early_warning_result_keeps_early_warning_score_and_source():
    result = {
        "mode": "Early Warning V1",
        "scope": "Norden",
        "horizon": "1m",
        "created_at": "2026-05-25T13:00:00",
        "candidates": [
            {
                "rank": 1,
                "ticker": "turn.st",
                "name": "Turn AB",
                "market": "Sverige",
                "early_warning_score": 83,
                "hidden_potential_score": 55,
                "catalyst_score": 76,
                "evidence_score": 70,
                "risk_score": 28,
                "signals": ["Fersk nyhet"],
                "news_evidence": [
                    {
                        "type": "Nyhet/katalysator",
                        "title": "Ny kontrakt",
                        "source": "Nasdaq Nordic",
                        "published": "2026-05-24",
                        "url": "https://example.test/contract",
                    }
                ],
            }
        ],
    }

    rows = radar_result_to_ranking_rows(result, selected_tickers=["TURN.ST"])
    ranked = radar_results_to_ranking_result(result)

    assert rows[0]["source"] == "Early Warning"
    assert rows[0]["decision_source"] == "Early Warning"
    assert rows[0]["ticker"] == "TURN.ST"
    assert rows[0]["score"] == 83
    assert rows[0]["early_warning_score"] == 83
    assert ranked.ranked[0].candidate.source == "Early Warning"
    assert ranked.ranked[0].candidate.evidence_items[0].source == "Nasdaq Nordic"


def test_radar_adapter_filters_selected_tickers_and_ignores_empty_candidates():
    result = {
        "analysis_engine": "Alpha Radar V2",
        "candidates": [
            {"ticker": "AAA.OL", "score": 80, "evidence_items": [{"type": "Nyhet", "title": "A"}]},
            {"ticker": "BBB.OL", "score": 70, "evidence_items": [{"type": "Nyhet", "title": "B"}]},
            {"ticker": "", "score": 99},
        ],
    }

    rows = radar_result_to_ranking_rows(result, selected_tickers=["BBB.OL"])

    assert [row["ticker"] for row in rows] == ["BBB.OL"]


def test_rank_local_sources_dedupes_radar_finansavisen_and_nbim_evidence():
    alpha = {
        "analysis_engine": "Alpha Radar V2",
        "candidates": [
            {
                "ticker": "KOG.OL",
                "name": "Kongsberg Gruppen",
                "market": "Norge",
                "hidden_potential_score": 72,
                "news_evidence": [{"type": "Nyhet", "title": "Kontrakt", "source": "Borsmelding"}],
            }
        ],
    }
    early = {
        "mode": "Early Warning V1",
        "candidates": [
            {
                "ticker": "KOG.OL",
                "name": "Kongsberg Gruppen",
                "market": "Norge",
                "early_warning_score": 81,
                "news_evidence": [{"type": "Nyhet/katalysator", "title": "Fersk ordre", "source": "NewsWeb"}],
            }
        ],
    }
    finansavisen_rows = [
        {
            "investor": "Investor A",
            "stock_name": "Kongsberg Gruppen",
            "matched_ticker": "KOG.OL",
            "side": "buy",
            "transaction_value_nok": 30_000_000,
            "estimated_date": "2026-05-20",
            "source_period": "1M",
            "source_periods": ["1M"],
        }
    ]
    nbim_overlay = {
        "KOG.OL": {
            "nbim_signal_score": 80,
            "nbim_change_type": "Okt",
            "nbim_market_value_nok": 1_500_000_000,
            "nbim_ticker_match_quality": "ticker",
            "nbim_evidence": [
                {
                    "type": "Oljefond",
                    "title": "NBIM/Oljefondet: Okt",
                    "source": "NBIM/Oljefondet",
                    "value": 1_500_000_000,
                }
            ],
        }
    }

    result = rank_local_evidence_sources(
        radar_results=[alpha, early],
        finansavisen_rows=finansavisen_rows,
        nbim_overlay=nbim_overlay,
        request={"max_count": 5},
    )
    row = result.ranked[0].as_dict()

    assert len(result.ranked) == 1
    assert row["ticker"] == "KOG.OL"
    assert "Alpha Radar" in row["source"]
    assert "Early Warning" in row["source"]
    assert "Finansavisen Bjellesauer" in row["source"]
    assert "Oljefond/NBIM" in row["source"]
    assert row["evidence_summary"]["totalt"] >= 4
    assert row["score"] >= 60







