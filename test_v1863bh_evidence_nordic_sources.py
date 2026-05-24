from pathlib import Path

import py_compile

from actor_registry import normalize_actor_row
from evidence_ledger import build_evidence_ledger, evidence_ledger_summary
from nordic_actor_insider_search import build_nordic_actor_search_plan, search_nordic_actor_insider
from source_budget import NEWSAPI_DAILY_FREE_LIMIT, estimate_source_budget, source_budget_text


def test_new_evidence_source_modules_compile():
    for name in [
        "evidence_ledger.py",
        "source_budget.py",
        "nordic_actor_insider_search.py",
        "actor_registry_ui.py",
        "alpha_radar_enrichment.py",
        "alpha_radar_engine.py",
        "early_warning_engine.py",
        "alpha_radar_results.py",
    ]:
        py_compile.compile(name, doraise=True)


def test_evidence_ledger_collects_nordic_actor_insider_and_articles():
    row = {
        "ticker": "TEST.OL",
        "nordic_actor_evidence": [{"type": "Bjellesau", "title": "Fant bjellesau: North Fund", "source": "NewsWeb"}],
        "nordic_insider_evidence": [{"type": "Insider", "title": "Primarinnsider kjop", "source": "NewsWeb"}],
        "articles": [{"title": "Kontrakt", "source": "E24", "url": "https://example.com/a"}],
    }

    ledger = build_evidence_ledger(row, found_by="test")

    assert len(ledger) == 3
    assert any(item["type"] == "Bjellesau" for item in ledger)
    assert any(item["type"] == "Insider" for item in ledger)
    assert "totalt 3" in evidence_ledger_summary({"evidence_ledger": ledger})


def test_nordic_actor_search_plan_and_result_use_actor_registry(monkeypatch):
    actor = normalize_actor_row({
        "active": True,
        "name": "North Fund",
        "aliases": "North Fund; NF Capital",
        "market": "Norge",
        "actor_type": "Bjellesau",
        "strength": "Sterk",
        "relevant_tickers": "TEST.OL",
    })

    import nordic_actor_insider_search as nordic

    monkeypatch.setattr(nordic, "load_actor_registry", lambda: [actor])

    def matcher(text, market=None, ticker=None, actor_types=None, rows=None):
        if "north fund" in str(text).lower() or "nf capital" in str(text).lower():
            return [dict(actor, matched_alias="North Fund")]
        return []

    monkeypatch.setattr(nordic, "match_actor_text", matcher)
    row = {"ticker": "TEST.OL", "name": "Test ASA", "market": "Norge"}
    plan = build_nordic_actor_search_plan(row)

    assert any("newsweb.oslobors.no" in item["query"] for item in plan)
    assert any("North Fund" in item["query"] or "NF Capital" in item["query"] for item in plan)
    assert all(item["api_cost"] == 0 for item in plan)

    def provider(query, limit=4, source="manual", days_back=None, language=None, domains=None):
        return ([
            {
                "title": "North Fund flagging in Test ASA",
                "description": "primary insider ownership and flagging",
                "source": "NewsWeb",
                "url": "https://example.com/newsweb",
                "published": "2026-05-24",
            }
        ], None)

    result = search_nordic_actor_insider(row, news_provider=provider, days_back=31, max_newsapi_queries=1)

    assert result["actor_evidence"]
    assert result["insider_evidence"]
    assert result["free_official_queries"] >= 1
    assert result["newsapi_requests_used"] == 1
    assert any("NewsAPI" in item["status"] for item in result["diagnostics"])


def test_source_budget_and_actor_registry_editor_static_guards():
    budget = estimate_source_budget(
        planned_tickers=25,
        source_values={"news": True, "insider": True, "results": True, "macro": True},
    )

    assert budget["newsapi_daily_free_limit"] == NEWSAPI_DAILY_FREE_LIMIT
    assert budget["actor_registry_checks"] == 25
    assert budget["free_official_queries"] >= 100
    assert "NewsAPI planlagt maks" in source_budget_text(budget)

    ui = Path("actor_registry_ui.py").read_text(encoding="utf-8", errors="ignore")
    assert "Legg til aktør" in ui
    assert "Slett valgte" in ui
    assert "Test aktør mot tekst" in ui
    assert "Unmatched Workbench" in ui
    assert "SelectboxColumn(\"Marked\"" in ui
