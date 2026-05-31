from nbim_radar import compare_nbim_holdings
from ranking_evidence_adapters import (
    apply_actor_registry_to_rows,
    finansavisen_to_ranking_rows,
    nbim_to_ranking_rows,
    rank_local_evidence_sources,
)
from ranking_service import rank_candidates


def test_finansavisen_adapter_preserves_actor_date_value_and_role():
    transactions = [
        {
            "investor": "Helge Gaso",
            "stock_name": "NORBIT",
            "matched_ticker": "NORBT.OL",
            "ticker_match_quality": "navn eksakt",
            "side": "buy",
            "transaction_value_nok": 19_820_000,
            "change_shares": 105_000,
            "new_ownership_pct": 0.16419,
            "performed_by": "FROY KAPITAL AS",
            "estimated_date": "2026-05-20",
            "source_period": "1D",
            "source_periods": ["1D", "1M"],
        }
    ]

    rows = finansavisen_to_ranking_rows(transactions)
    evidence = rows[0]["bjellesau_evidence"][0]
    ranked = rank_candidates(rows)
    ranked_evidence = ranked.ranked[0].candidate.evidence_items[0]

    assert rows[0]["ticker"] == "NORBT.OL"
    assert rows[0]["source"] == "Finansavisen Bjellesauer"
    assert evidence["actor"] == "Helge Gaso"
    assert evidence["date"] == "2026-05-20"
    assert evidence["value"] == 19_820_000
    assert evidence["actor_roles"] == ["Bjellesau"]
    assert ranked_evidence.actor == "Helge Gaso"
    assert ranked_evidence.value == 19_820_000


def test_nbim_adapter_preserves_change_value_and_institution_role():
    changes = compare_nbim_holdings(
        [{"ticker": "AAA", "name": "A", "ownership_pct": 1.0, "market_value_nok": 100_000_000}],
        [{"ticker": "AAA", "name": "A", "ownership_pct": 1.5, "market_value_nok": 250_000_000}],
    )

    rows = nbim_to_ranking_rows(changes)
    row = rows[0]
    evidence = row["nbim_evidence"][0]
    ranked = rank_candidates(rows)

    assert row["ticker"] == "AAA"
    assert row["source"] == "Oljefond/NBIM"
    assert row["market_cap"] == 250_000_000
    assert evidence["actor"] == "Norges Bank Investment Management"
    assert "Institusjon" in evidence["actor_roles"]
    assert "Oljefond" in evidence["actor_roles"]
    assert evidence["value"] == 250_000_000
    assert evidence["direction"] == "Okt"
    assert ranked.ranked[0].candidate.evidence_items[0].actor == "Norges Bank Investment Management"


def test_actor_registry_adapter_adds_multiple_roles_without_duplicate_actor():
    actor_rows = [
        {
            "active": True,
            "name": "North Fund",
            "aliases": "North Fund; NF Capital",
            "market": "Norge",
            "actor_roles": "Bjellesau; Insider watch",
            "strength": "Sterk",
            "trust_level": "Bekreftet",
            "relevant_tickers": "TEST.OL",
        }
    ]
    base_rows = [
        {
            "ticker": "TEST.OL",
            "name": "Test ASA",
            "market": "Norge",
            "source": "Alpha Radar",
            "score": 55,
            "why_now": "NF Capital kjoper mer i Test ASA.",
        }
    ]

    enriched = apply_actor_registry_to_rows(base_rows, actor_rows=actor_rows)
    row = enriched[0]
    evidence = row["actor_registry_evidence"][0]

    assert evidence["actor"] == "North Fund"
    assert evidence["actor_roles"] == ["Bjellesau", "Insider watch"]
    assert len(row["actor_registry_evidence"]) == 1
    assert row["bjellesau_score"] >= 80
    assert row["insider_score"] >= 80
    assert row["bjellesau_evidence"][0]["actor"] == "North Fund"
    assert row["insider_evidence"][0]["actor"] == "North Fund"


def test_rank_local_evidence_sources_combines_sources_and_dedupes_same_ticker():
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
    nbim_changes = compare_nbim_holdings(
        [{"ticker": "KOG.OL", "name": "Kongsberg Gruppen", "ownership_pct": 1.0, "market_value_nok": 1_000_000_000}],
        [{"ticker": "KOG.OL", "name": "Kongsberg Gruppen", "ownership_pct": 1.4, "market_value_nok": 1_500_000_000}],
    )

    result = rank_local_evidence_sources(
        finansavisen_rows=finansavisen_rows,
        nbim_changes=nbim_changes,
        request={"max_count": 5},
    )
    row = result.ranked[0].as_dict()

    assert result.status == "ok"
    assert len(result.ranked) == 1
    assert row["ticker"] == "KOG.OL"
    assert "Finansavisen Bjellesauer" in row["source"]
    assert "Oljefond/NBIM" in row["source"]
    assert row["evidence_summary"]["totalt"] == 2
    assert row["recommended_action"] in {"Til beslutningsgrunnlag", "Analyser videre"}




