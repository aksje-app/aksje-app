from pathlib import Path

from ranking_service import (
    EvidenceItem,
    RankingRequest,
    UniverseCandidate,
    rank_candidates,
    score100,
)


def test_score100_accepts_unit_percent_and_comma_values():
    assert score100(0.82) == 82.0
    assert score100("82") == 82.0
    assert score100("82,5 %") == 82.5
    assert score100("193.407.647.744 NOK") == 100.0


def test_ranking_normalizes_evidence_and_score_components():
    result = rank_candidates(
        [
            {
                "ticker": "abc.ol",
                "name": "ABC ASA",
                "market": "Norge",
                "source": "Alpha Radar",
                "score": 92,
                "insider_score": 0.8,
                "catalyst_score": 85,
                "volume_score": 85,
                "risk_score": 20,
                "data_quality": "ekte",
                "insider_evidence": [
                    {
                        "type": "Insider",
                        "title": "Primarinnsider kjop",
                        "source": "NewsWeb",
                        "actor": "Kari CEO",
                        "strength": "Sterk",
                        "url": "https://example.test/insider",
                    }
                ],
                "news_evidence": [
                    {
                        "type": "Nyhet/katalysator",
                        "title": "Kontrakt",
                        "source": "Borsmelding",
                    }
                ],
            }
        ]
    )

    assert result.status == "ok"
    row = result.ranked[0]
    assert row.rank == 1
    assert row.candidate.ticker == "ABC.OL"
    assert row.score >= 75
    assert row.recommended_action == "Til beslutningsgrunnlag"
    assert row.evidence_summary["totalt"] == 2
    assert {component.name for component in row.score_components} == {
        "base",
        "evidence",
        "ownership",
        "catalyst",
        "timing",
        "quality",
        "risk_inverse",
    }


def test_ranking_dedupes_same_ticker_and_merges_sources_and_evidence():
    result = rank_candidates(
        [
            {
                "ticker": "KOG.OL",
                "name": "Kongsberg Gruppen",
                "market": "Norge",
                "source": "Finansavisen Bjellesauer",
                "score": 96,
                "bjellesau_evidence": [
                    {"type": "Bjellesau", "title": "Flere kjop", "source": "Finansavisen", "actor": "Investor A"}
                ],
            },
            {
                "ticker": "KOG.OL",
                "name": "Kongsberg Gruppen",
                "market": "Norge",
                "source": "Oljefond Radar",
                "score": 72,
                "nbim_signal_score": 85,
                "nbim_evidence": [
                    {"type": "NBIM/Oljefond", "title": "Ny/okt posisjon", "source": "NBIM"}
                ],
            },
        ]
    )

    assert len(result.ranked) == 1
    row = result.ranked[0].as_dict()
    assert row["ticker"] == "KOG.OL"
    assert "Finansavisen Bjellesauer" in row["source"]
    assert "Oljefond Radar" in row["source"]
    assert row["evidence_summary"]["totalt"] == 2
    assert row["candidate"]["metadata"]["merged_count"] == 2


def test_ranking_request_filters_markets_sources_and_limits():
    rows = [
        {"ticker": "AAA.OL", "market": "Norge", "source": "Finansavisen Bjellesauer", "score": 90},
        {"ticker": "BBB.ST", "market": "Sverige", "source": "Finansavisen Bjellesauer", "score": 95},
        {"ticker": "CCC.OL", "market": "Norge", "source": "Alpha Radar", "score": 99},
    ]

    result = rank_candidates(
        rows,
        RankingRequest(max_count=1, markets=("Norge",), sources=("Finansavisen",)),
    )

    assert [row.candidate.ticker for row in result.ranked] == ["AAA.OL"]
    assert result.summary["normalized_candidates"] == 1


def test_empty_and_require_evidence_paths_are_stable():
    assert rank_candidates([]).status == "empty"

    result = rank_candidates(
        [{"ticker": "NOEVID.OL", "score": 99, "market": "Norge"}],
        {"require_evidence": True},
    )

    assert result.status == "empty"
    assert result.ranked == ()


def test_risk_penalty_and_flags_lower_risky_candidate():
    low_risk = UniverseCandidate.from_mapping(
        {
            "ticker": "SAFE.OL",
            "score": 70,
            "catalyst_score": 50,
            "risk_score": 20,
            "data_quality": "ekte",
            "news_evidence": [{"type": "Nyhet", "title": "Bekreftet kontrakt"}],
        }
    )
    high_risk = UniverseCandidate.from_mapping(
        {
            "ticker": "RISK.OL",
            "score": 70,
            "catalyst_score": 50,
            "risk_score": 90,
            "data_quality": "ekte",
            "news_evidence": [{"type": "Nyhet", "title": "Bekreftet kontrakt"}],
        }
    )

    result = rank_candidates([high_risk, low_risk])
    rows = {row.candidate.ticker: row for row in result.ranked}

    assert rows["SAFE.OL"].score > rows["RISK.OL"].score
    assert "hoy risiko" in rows["RISK.OL"].risk_flags


def test_evidence_item_serializes_roles_without_ui_dependency():
    item = EvidenceItem.from_mapping(
        {
            "type": "Bjellesau",
            "actor_roles": ["Bjellesau", "Insider watch"],
            "title": "Kjop",
        },
        ticker="TEST.OL",
    )

    assert item.as_dict()["actor_roles"] == ["Bjellesau", "Insider watch"]

    source = Path(__import__("ranking_service").__file__).read_text(encoding="utf-8")
    assert "streamlit" not in source.lower()




