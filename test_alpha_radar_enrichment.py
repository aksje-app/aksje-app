import alpha_radar_enrichment as enrichment_mod
from alpha_radar_enrichment import enrich_alpha_radar_row, infer_macro_themes


def fake_news_provider(query, limit=8, source="manual"):
    assert source == "manual"
    return [
        {"title": "Small offshore supplier wins strong contract", "description": "Order backlog and margin guidance improve."},
        {"title": "Local investor buys after turnaround", "description": "Positive restructuring update."},
    ], None


def fake_insider_provider(ticker):
    return {
        "score": 0.68,
        "label": "Positivt insiderbilde",
        "buy_count": 3,
        "sell_count": 0,
        "latest_type": "BUY",
        "latest_date": "2026-05-20",
        "transactions": 3,
        "latest_transactions": [
            {"name": "Jane Founder", "relation": "CEO", "type": "BUY", "days_ago": 2},
            {"name": "Board Member", "relation": "Director", "type": "BUY", "days_ago": 9},
        ],
    }


def fake_earnings_provider(ticker):
    return {"days_until": 21, "date": "2026-06-12", "error": None}


def test_enrichment_adds_real_signal_proxies_without_network(monkeypatch):
    monkeypatch.setattr(enrichment_mod, "match_actor_text", lambda *args, **kwargs: [])
    monkeypatch.setattr(enrichment_mod, "record_actor_hits", lambda *args, **kwargs: 0)
    monkeypatch.setattr(enrichment_mod, "search_financial_evidence", lambda *args, **kwargs: {"articles": [], "actor_evidence": [], "insider_evidence": [], "diagnostics": [], "errors": []})
    monkeypatch.setattr(enrichment_mod, "search_nordic_actor_insider", lambda *args, **kwargs: {"articles": [], "actor_evidence": [], "insider_evidence": [], "diagnostics": [], "errors": []})
    row = {
        "ticker": "HIDE.OL",
        "name": "Hidden Offshore Supplier",
        "sector": "Offshore oil service",
        "score": 6.1,
        "market_cap": 800_000_000,
        "profit_margin": 0.08,
        "revenue_growth": 0.18,
        "score_parts": {"quality": 0.62, "fundamental_growth": 0.71, "value": 0.64},
    }
    commodity_snapshot = {
        "brent_oil": {"ret_1m": 8.0, "ret_3m": 14.0},
        "wti_oil": {"ret_1m": 7.0, "ret_3m": 12.0},
    }

    enriched = enrich_alpha_radar_row(
        row,
        ticker="HIDE.OL",
        include_news=True,
        include_insider=True,
        include_macro=True,
        include_results=True,
        mode="Ravare/makro-medvind",
        active_signals=["Nyheter/katalysator", "Insider/bjellesauer", "Ravarer/makro", "Resultater"],
        news_provider=fake_news_provider,
        insider_provider=fake_insider_provider,
        earnings_provider=fake_earnings_provider,
        commodity_snapshot=commodity_snapshot,
    )

    assert enriched["news_count"] >= 2
    assert enriched["small_news_big_impact_score"] > 0.6
    assert enriched["insider_quality_score"] > 0.75
    assert enriched["bjellesau_score"] is None
    assert enriched["insider_evidence"]
    assert not enriched["bjellesau_evidence"]
    assert enriched["macro_tailwind_score"] > 0.6
    assert "oil_service" in enriched["macro_themes"]
    assert enriched["result_inflection_score"] > 0.55
    assert enriched["earnings_days_until"] == 21


def test_macro_theme_inference_uses_second_order_sector_text():
    themes = infer_macro_themes({"ticker": "SHIP.ST", "name": "Nordic Shipping", "industry": "Dry bulk shipping"})
    assert "shipping" in themes




