from actor_registry import actor_aliases_for_matching, actor_registry_to_csv, match_actor_text, normalize_actor_row, parse_actor_registry_upload
from decision_engine import build_decision_case
from early_warning_engine import run_early_warning
from financial_evidence_search import build_financial_search_plan, search_financial_evidence
from nbim_radar import build_nbim_overlay, compare_nbim_holdings, parse_number, read_nbim_csv_bytes
from nordic_market_sources import local_market_source_diagnostics, local_news_queries


def test_actor_registry_alias_matching_marks_bjellesau():
    rows = [
        normalize_actor_row({
            "active": True,
            "name": "North Fund",
            "aliases": "North Fund; NF Capital",
            "market": "Norge",
            "actor_type": "Bjellesau",
            "strength": "Sterk",
            "relevant_tickers": "TEST.OL",
        })
    ]

    aliases = actor_aliases_for_matching(market="Norge", ticker="TEST.OL", rows=rows)
    matches = match_actor_text("NF Capital kjoper mer aksjer", market="Norge", ticker="TEST.OL", rows=rows)

    assert "north fund" in aliases
    assert matches[0]["name"] == "North Fund"
    assert not match_actor_text("NF Capital", market="Norge", ticker="OTHER.OL", rows=rows)
    assert not match_actor_text("NF Capital", market="USA", ticker="TEST", rows=rows)


def test_nordic_market_sources_add_local_diagnostics_and_queries():
    row = {"ticker": "EQNR.OL", "name": "Equinor", "market": "Norge"}
    diagnostics = local_market_source_diagnostics(row, horizon="6m")
    queries = local_news_queries("EQNR.OL", "Equinor", "Norge")

    assert diagnostics
    assert any("NewsWeb" in item["source"] for item in diagnostics)
    assert any("primarinnsider" in query for query in queries)


def test_early_warning_uses_result_inflection_proxy_when_earnings_missing():
    def provider(ticker, use_news=False, include_insider=False):
        return {
            "ticker": ticker,
            "name": "Turnaround",
            "score": 7.1,
            "ret_1m": 0.08,
            "ret_3m": 0.02,
            "ret_6m": -0.18,
            "volatility": 0.025,
            "max_drawdown": -0.16,
            "market_cap": 1_200_000_000,
            "result_inflection_score": 0.67,
            "result_inflection_quality": "beregnet",
            "score_parts": {"momentum": 0.64, "trend": 0.58, "volume": 0.61},
        }

    result = run_early_warning(["TURN.OL"], limit=1, max_scan=1, include_news=False, include_insider=False, score_provider=provider)
    candidate = result["candidates"][0]

    assert candidate["inflection_score"] >= 60
    assert candidate["factor_quality"]["earnings_surprise"] == "beregnet"


def test_nbim_compare_overlay_and_decision_signal():
    previous = [
        {"ticker": "AAA", "name": "A", "shares": 100, "ownership_pct": 1.0},
        {"ticker": "OLD", "name": "Old", "shares": 100},
    ]
    current = [
        {"ticker": "AAA", "name": "A", "shares": 125, "ownership_pct": 1.2},
        {"ticker": "NEW", "name": "New", "shares": 10, "ownership_pct": 0.4},
    ]

    changes = compare_nbim_holdings(previous, current)
    overlay = build_nbim_overlay(changes)

    assert parse_number("193.407.647.744") == 193407647744.0
    assert overlay["AAA"]["nbim_change_type"] == "Okt"
    assert overlay["NEW"]["nbim_change_type"] == "Ny"
    assert any(row["change_type"] == "Solgt ut" and row["ticker"] == "OLD" for row in changes)

    case = build_decision_case({
        "ticker": "AAA",
        "hidden_potential_score": 78,
        "evidence_score": 62,
        "risk_score": 32,
        "volume_score": 63,
        "evidence_items": [{"type": "nyhet"}],
        **overlay["AAA"],
    })

    assert case["nbim_count"] == 1
    assert any("Oljefond" in reason or "NBIM" in reason for reason in case["positive_reasons"])


def test_nbim_utf16_equity_csv_and_name_matching():
    csv_text = (
        "Region;Country;Name;Industry;Market Value(NOK);Market Value(USD);Voting;Ownership;Incorporation Country\n"
        "Europe;Denmark;Novo Nordisk A/S;Health Care;36836769106;3651959637;0.51%;1.6%;\n"
        "Europe;Finland;Nokia Oyj;Telecommunications;5618011511;556963920;1.48%;1.48%;\n"
    )
    rows = read_nbim_csv_bytes(csv_text.encode("utf-16"))
    overlay = build_nbim_overlay(compare_nbim_holdings([], rows))

    assert rows[0]["market_value_nok"] == 36836769106.0
    assert overlay["NOVO-B.CO"]["nbim_ticker_match_quality"] == "navn eksakt"
    assert overlay["NOKIA.HE"]["nbim_change_type"] == "Ny"


def test_actor_registry_csv_roundtrip_and_financial_search_plan():
    rows = [normalize_actor_row({"active": True, "name": "North Fund", "aliases": "NF", "market": "Alle", "actor_type": "Bjellesau"})]
    parsed = parse_actor_registry_upload(actor_registry_to_csv(rows), "actors.csv")
    assert parsed[0]["name"] == "North Fund"

    plan = build_financial_search_plan({"ticker": "NOVO-B.CO", "name": "Novo Nordisk", "market": "Danmark"})
    assert any("Novo Nordisk" in item["query"] for item in plan)

    def provider(query, limit=4, source="manual", days_back=None, language=None, domains=None):
        return ([{"title": "NF flagging in Novo Nordisk", "description": "primary insider and ownership", "source": "Test", "url": "https://example.com"}], None)

    result = search_financial_evidence({"ticker": "NOVO-B.CO", "name": "Novo Nordisk", "market": "Danmark"}, news_provider=provider, days_back=31, max_queries=1)
    assert result["articles"]
    assert result["insider_evidence"]
