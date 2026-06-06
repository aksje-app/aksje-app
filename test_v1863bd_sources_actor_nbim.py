from actor_registry import actor_aliases_for_matching, actor_registry_to_csv, match_actor_text, normalize_actor_row, parse_actor_registry_upload
from decision_engine import build_decision_case
from early_warning_engine import run_early_warning
from financial_evidence_search import build_financial_search_plan, search_financial_evidence
from nbim_radar import (
    annotate_nbim_changes,
    build_nbim_overlay,
    build_nbim_priority_views,
    build_nbim_watchlist,
    compare_nbim_holdings,
    format_nbim_amount,
    nbim_changes_to_display_rows,
    nbim_group_summary,
    parse_number,
    read_nbim_csv_bytes,
)
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


def test_nbim_priority_views_and_display_units():
    previous = [
        {"ticker": "AAA", "name": "A", "ownership_pct": 2.0, "market_value_nok": 100_000_000},
        {"ticker": "SELL", "name": "Sold", "ownership_pct": 1.0, "market_value_nok": 900_000_000},
    ]
    current = [
        {"ticker": "AAA", "name": "A", "ownership_pct": 4.16, "market_value_nok": 2_610_898_841, "market_value_usd": 258_841_843},
        {"ticker": "NEW", "name": "New", "ownership_pct": 0.2, "market_value_nok": 25_000_000},
    ]

    changes = compare_nbim_holdings(previous, current)
    views = build_nbim_priority_views(changes, limit=10)
    top_display = nbim_changes_to_display_rows(views["Topp signaler"])

    assert format_nbim_amount(2_610_898_841, "NOK") == "2.610.898.841 NOK"
    assert top_display[0]["Ticker"] == "AAA"
    assert top_display[0]["Malt verdi"] == "eierandel"
    assert top_display[0]["Naa-verdi"] == "4,16 %"
    assert top_display[0]["Markedsverdi NOK"] == "2.610.898.841 NOK"
    assert views["Solgt ut"][0]["ticker"] == "SELL"


def test_nbim_matching_ignores_two_letter_ticker_root_noise():
    rows = [{"name": "Alpek SAB de CV", "country": "Mexico", "market_value_nok": 611_481_793, "ownership_pct": 5.6}]
    overlay = build_nbim_overlay(compare_nbim_holdings([], rows))

    assert "DE" not in overlay


def test_nbim_advanced_signals_watchlist_overlap_and_us_alias():
    previous = [
        {"name": "Weak Accumulator Inc", "country": "United States", "ownership_pct": 1.0, "voting_pct": 1.0, "market_value_nok": 2_000_000_000},
        {"name": "Caterpillar Inc", "country": "United States", "ownership_pct": 1.2, "voting_pct": 1.2, "market_value_nok": 24_000_000_000},
        {"name": "Schlumberger NV", "country": "United States", "ownership_pct": 1.3, "voting_pct": 1.3, "market_value_nok": 8_200_000_000},
    ]
    current = [
        {"name": "Weak Accumulator Inc", "country": "United States", "ownership_pct": 1.5, "voting_pct": 2.3, "market_value_nok": 1_500_000_000},
        {"name": "SLB Ltd", "country": "United States", "ownership_pct": 1.39, "voting_pct": 1.39, "market_value_nok": 8_045_615_678},
    ]

    changes = compare_nbim_holdings(previous, current)
    annotated = annotate_nbim_changes(changes, radar_tickers=["SLB"])
    views = build_nbim_priority_views(annotated, limit=10)
    watchlist = build_nbim_watchlist(annotated, limit=10)
    groups = nbim_group_summary(annotated, "country")
    slb = next(row for row in annotated if row.get("matched_ticker") == "SLB")
    weak = next(row for row in annotated if row.get("name") == "Weak Accumulator Inc")

    assert slb["radar_overlap"] is True
    assert "Radar-overlap" in slb["nbim_signals"]
    assert "Mulig navnebytte/dobbeltmatch" in slb["nbim_signals"]
    assert "Akkumulering i svakhet" in weak["nbim_signals"]
    assert "Stemmeavvik" in weak["nbim_signals"]
    assert any(row.get("change_type") == "Solgt ut" and row.get("matched_ticker") == "CAT" for row in annotated)
    overlay = build_nbim_overlay(annotated)
    assert overlay["SLB"]["nbim_change_type"] == "Ny"
    assert views["Unmatched verdi"]
    assert watchlist
    assert groups[0]["Rotasjon"] in {"Inn", "Ut", "Blandet"}


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








