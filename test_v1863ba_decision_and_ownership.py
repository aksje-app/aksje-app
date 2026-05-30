from alpha_radar_engine import run_alpha_radar
from alpha_radar_ownership import classify_ownership_item, split_ownership_evidence
from decision_engine import build_decision_case, decision_source_rows_from_radar_result
from early_warning_engine import run_early_warning


def _radar_row(ticker="TEST.OL"):
    return {
        "ticker": ticker,
        "name": "Test Case",
        "market": "Norge",
        "score": 7.8,
        "ret_1m": 0.08,
        "ret_3m": 0.16,
        "ret_6m": 0.05,
        "volatility": 0.022,
        "max_drawdown": -0.12,
        "market_cap": 1_900_000_000,
        "catalyst_score": 0.72,
        "estimate_revision_score": 0.70,
        "earnings_surprise_score": 0.66,
        "revenue_growth": 0.18,
        "profit_margin": 0.12,
        "latest_transactions": [
            {
                "name": "Kari CEO",
                "relation": "CEO",
                "type": "BUY",
                "date": "2026-05-22",
                "shares": 10000,
                "url": "https://example.com/insider",
            },
            {
                "name": "North Fund",
                "relation": "Fund investor",
                "type": "BUY",
                "date": "2026-05-22",
                "shares": 50000,
                "url": "https://example.com/owner",
            },
        ],
        "articles": [
            {
                "title": "Contract win",
                "source": "Exchange",
                "published": "2026-05-22",
                "url": "https://example.com/news",
            }
        ],
        "score_parts": {
            "momentum": 0.72,
            "trend": 0.70,
            "volume": 0.76,
            "quality": 0.66,
            "fundamental_growth": 0.68,
            "debt": 0.64,
            "value": 0.62,
        },
    }


def test_ownership_split_marks_insider_and_bjellesau_separately():
    assert classify_ownership_item({"name": "Kari", "relation": "CEO"}) == "Insider"
    assert classify_ownership_item({"name": "North Fund", "relation": "Fund investor"}) == "Bjellesau"

    combined, insider, bjellesau = split_ownership_evidence(_radar_row(), limit=8)

    assert {item["type"] for item in combined} >= {"Insider", "Bjellesau"}
    assert insider[0]["title"] == "Kari CEO"
    assert bjellesau[0]["title"] == "North Fund"


def test_alpha_and_early_warning_emit_separate_ownership_scores():
    def provider(ticker, use_news=False, include_insider=False):
        return _radar_row(ticker)

    alpha = run_alpha_radar(
        ["TEST.OL"],
        limit=1,
        max_scan=1,
        include_news=True,
        include_insider=True,
        score_provider=provider,
    )
    early = run_early_warning(
        ["TEST.OL"],
        limit=1,
        max_scan=1,
        include_news=True,
        include_insider=True,
        score_provider=provider,
    )

    alpha_candidate = alpha["candidates"][0]
    early_candidate = early["candidates"][0]

    assert alpha_candidate["insider_score"] is not None
    assert alpha_candidate["bjellesau_score"] is not None
    assert alpha_candidate["insider_evidence"][0]["type"] == "Insider"
    assert alpha_candidate["bjellesau_evidence"][0]["type"] == "Bjellesau"
    assert early_candidate["insider_score"] is not None
    assert early_candidate["bjellesau_score"] is not None
    assert early_candidate["bjellesau_evidence"][0]["title"] == "North Fund"


def test_decision_engine_produces_manual_buy_wait_avoid_basis():
    strong = {
        **_radar_row(),
        "hidden_potential_score": 86,
        "evidence_score": 72,
        "insider_score": 70,
        "bjellesau_score": 66,
        "volume_score": 65,
        "risk_score": 30,
        "liquidity_penalty": 2,
        "insider_evidence": [{"type": "Insider", "title": "Kari CEO"}],
        "bjellesau_evidence": [{"type": "Bjellesau", "title": "North Fund"}],
        "news_evidence": [{"type": "nyhet", "title": "Contract"}],
        "evidence_items": [{"type": "Insider"}, {"type": "Bjellesau"}, {"type": "nyhet"}],
    }
    risky = {
        **strong,
        "ticker": "RISK.OL",
        "hidden_potential_score": 55,
        "evidence_score": 30,
        "risk_score": 85,
        "reject_reasons": ["hoy volatilitet/drawdown"],
        "evidence_items": [],
    }

    assert build_decision_case(strong)["decision"] == "Kjop naa"
    assert build_decision_case(risky)["decision"] == "Unnga"


def test_decision_source_rows_can_select_subset_from_radar_result():
    result = {
        "mode": "Early Warning V1",
        "created_at": "2026-05-23 12:00",
        "scope": "Norge",
        "candidates": [_radar_row("AAA.OL"), _radar_row("BBB.OL")],
    }

    rows = decision_source_rows_from_radar_result(result, ["BBB.OL"])

    assert len(rows) == 1
    assert rows[0]["ticker"] == "BBB.OL"
    assert rows[0]["decision_source"] == "Early Warning"



