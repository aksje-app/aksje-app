import py_compile

import financial_evidence_search
import nordic_actor_insider_search
from actor_registry import normalize_actor_row
from alpha_radar_engine import run_alpha_radar
from early_warning_engine import run_early_warning
from source_budget import estimate_source_budget


def _base_row(ticker="TEST.OL"):
    return {
        "ticker": ticker,
        "name": "Test ASA",
        "market": "Norge",
        "score": 6.4,
        "ret_1m": 0.03,
        "ret_3m": -0.04,
        "ret_6m": -0.08,
        "ret_1y": -0.15,
        "volatility": 0.03,
        "max_drawdown": -0.22,
        "market_cap": 1_200_000_000,
        "profit_margin": 0.08,
        "revenue_growth": 0.12,
    }


def test_actor_first_open_web_search_can_create_actor_evidence(monkeypatch):
    actor = normalize_actor_row({
        "active": True,
        "name": "North Person",
        "aliases": "North Person; NP Holding",
        "market": "Norge",
        "actor_roles": "Bjellesau; Insider watch",
        "relevant_tickers": "TEST.OL",
        "strength": "Sterk",
    })

    monkeypatch.setattr(financial_evidence_search, "load_actor_registry", lambda: [actor])
    monkeypatch.setattr(financial_evidence_search, "record_actor_hits", lambda *args, **kwargs: 1)

    def fake_gdelt(query, **kwargs):
        assert "North Person" in query or "NP Holding" in query
        return ([{"title": "Test ASA flagging notice", "source": "dn.no", "url": "https://example.com/test"}], None)

    monkeypatch.setattr(financial_evidence_search, "search_open_web_articles", fake_gdelt)
    result = financial_evidence_search.search_financial_evidence(
        _base_row(),
        news_provider=None,
        days_back=31,
        max_queries=1,
        max_open_web_queries=1,
    )

    assert result["open_web_requests_used"] == 1
    assert result["actor_evidence"]
    assert result["actor_evidence"][0]["actor_roles"] == ["Bjellesau", "Insider watch"]


def test_nordic_actor_plan_puts_actor_registry_before_generic_links(monkeypatch):
    actor = normalize_actor_row({
        "active": True,
        "name": "North Person",
        "aliases": "North Person",
        "market": "Norge",
        "actor_roles": "Bjellesau",
        "relevant_tickers": "TEST.OL",
    })
    monkeypatch.setattr(nordic_actor_insider_search, "load_actor_registry", lambda: [actor])
    plan = nordic_actor_insider_search.build_nordic_actor_search_plan(_base_row())

    assert plan
    assert "register" in str(plan[0]["type"]).lower()
    assert "North Person" in plan[0]["query"]


def test_alpha_radar_hard_evidence_gate_blocks_generic_top_30():
    no_evidence = run_alpha_radar(
        ["TEST.OL"],
        include_news=True,
        include_insider=True,
        active_signals=["Insider/bjellesauer", "Nyheter/katalysator"],
        fill_low_data=False,
        score_provider=lambda ticker, **kwargs: _base_row(ticker),
        limit=10,
        max_scan=10,
    )

    assert no_evidence["candidate_count"] == 0
    assert no_evidence["excluded_count"] == 1
    assert "mangler konkret insider-/bjellesau-evidence" in no_evidence["excluded_reason_counts"]
    assert "mangler konkret nyhets-/katalysator-evidence" in no_evidence["excluded_reason_counts"]

    row = _base_row()
    row["articles"] = [{"title": "Kontrakt", "source": "NewsWeb", "url": "https://example.com/news"}]
    row["bjellesau_evidence"] = [{"title": "North Person", "source": "GDELT", "url": "https://example.com/actor"}]
    with_evidence = run_alpha_radar(
        ["TEST.OL"],
        include_news=True,
        include_insider=True,
        active_signals=["Insider/bjellesauer", "Nyheter/katalysator"],
        fill_low_data=False,
        score_provider=lambda ticker, **kwargs: row,
        limit=10,
        max_scan=10,
    )

    assert with_evidence["candidate_count"] == 1


def test_early_warning_hard_evidence_gate_blocks_empty_candidates():
    no_evidence = run_early_warning(
        ["TEST.OL"],
        include_news=True,
        include_insider=True,
        score_provider=lambda ticker, **kwargs: _base_row(ticker),
        limit=10,
        max_scan=10,
    )

    assert no_evidence["candidate_count"] == 0
    assert no_evidence["excluded_count"] == 1

    row = _base_row()
    row["articles"] = [{"title": "Flagging", "source": "NewsWeb", "url": "https://example.com/news"}]
    row["financial_insider_evidence"] = [{"title": "Primarinnsider kjop", "source": "GDELT", "url": "https://example.com/inside"}]
    with_evidence = run_early_warning(
        ["TEST.OL"],
        include_news=True,
        include_insider=True,
        score_provider=lambda ticker, **kwargs: row,
        limit=10,
        max_scan=10,
    )

    assert with_evidence["candidate_count"] == 1


def test_open_web_budget_and_modules_compile():
    for name in [
        "open_web_news_search.py",
        "financial_evidence_search.py",
        "nordic_actor_insider_search.py",
        "alpha_radar_engine.py",
        "early_warning_engine.py",
        "actor_registry_ui.py",
    ]:
        py_compile.compile(name, doraise=True)
    budget = estimate_source_budget(planned_tickers=25, source_values={"news": True, "insider": True})
    assert budget["open_web_gdelt_calls"] == 75




