from pathlib import Path

import py_compile

import financial_evidence_search
import nordic_actor_insider_search
from actor_registry import (
    actor_aliases_for_matching,
    actor_match_evidence,
    actor_registry_to_csv,
    actor_roles,
    match_actor_text,
    normalize_actor_row,
    parse_actor_registry_upload,
)


def test_actor_registry_multi_roles_roundtrip_and_matching():
    row = normalize_actor_row({
        "active": True,
        "name": "North Person",
        "aliases": "North Person; NP Holding",
        "market": "Norden",
        "actor_roles": "Bjellesau; Insider watch",
        "strength": "Sterk",
        "trust_level": "Bekreftet",
    })

    assert actor_roles(row) == ["Bjellesau", "Insider watch"]
    assert row["actor_type"] == "Bjellesau"
    assert match_actor_text("NP Holding flagging", market="Norge", ticker="TEST.OL", rows=[row], actor_types=("Insider watch",))
    assert "np holding" in actor_aliases_for_matching(market="Norge", ticker="TEST.OL", rows=[row], actor_types=("Bjellesau",))

    evidence = actor_match_evidence("North Person kjoper", market="Norge", ticker="TEST.OL")
    # Global registry may be empty in test env; direct match is covered above.
    assert isinstance(evidence, list)

    parsed = parse_actor_registry_upload(actor_registry_to_csv([row]), "actors.csv")
    assert parsed[0]["actor_roles"] == "Bjellesau; Insider watch"
    assert parsed[0]["trust_level"] == "Bekreftet"


def test_financial_and_nordic_sources_label_combined_roles(monkeypatch):
    actor = normalize_actor_row({
        "active": True,
        "name": "North Person",
        "aliases": "North Person",
        "market": "Norge",
        "actor_roles": "Bjellesau; Insider watch",
        "strength": "Sterk",
        "trust_level": "Bekreftet",
        "relevant_tickers": "TEST.OL",
    })

    def matcher(text, market=None, ticker=None, actor_types=None, rows=None):
        if "north person" in str(text).lower():
            return [dict(actor, matched_alias="North Person")]
        return []

    monkeypatch.setattr(financial_evidence_search, "match_actor_text", matcher)
    monkeypatch.setattr(financial_evidence_search, "record_actor_hits", lambda *args, **kwargs: 1)
    monkeypatch.setattr(nordic_actor_insider_search, "match_actor_text", matcher)
    monkeypatch.setattr(nordic_actor_insider_search, "record_actor_hits", lambda *args, **kwargs: 1)

    def provider(query, limit=4, source="manual", days_back=None, language=None, domains=None):
        return ([{"title": "North Person flagging", "description": "primary insider ownership", "source": "NewsWeb", "url": "https://example.com"}], None)

    fin = financial_evidence_search.search_financial_evidence(
        {"ticker": "TEST.OL", "name": "Test ASA", "market": "Norge"},
        news_provider=provider,
        days_back=31,
        max_queries=1,
    )
    nordic = nordic_actor_insider_search.search_nordic_actor_insider(
        {"ticker": "TEST.OL", "name": "Test ASA", "market": "Norge"},
        news_provider=provider,
        days_back=31,
        max_newsapi_queries=1,
    )

    assert "bjellesau/insider-watch" in fin["actor_evidence"][0]["title"].lower()
    assert fin["actor_evidence"][0]["actor_roles"] == ["Bjellesau", "Insider watch"]
    assert "trust_level" in nordic["actor_evidence"][0]


def test_actor_registry_ui_roles_search_sort_and_privacy_static_guards():
    for name in ["actor_registry.py", "actor_registry_ui.py", "financial_evidence_search.py", "nordic_actor_insider_search.py"]:
        py_compile.compile(name, doraise=True)

    ui = Path("actor_registry_ui.py").read_text(encoding="utf-8", errors="ignore")
    assert "actor_registry_search_v1863bj" in ui
    assert "actor_registry_sort_v1863bj" in ui
    assert "actor_registry_selected_actor_v1863bj" in ui
    assert "Raske alias-forslag" in ui
    assert "actor_registry_refresh_hits_v1863bj" in ui
    assert "Lagres lokalt" in ui
    assert "actor_roles" in ui
    assert "st.data_editor" not in ui



