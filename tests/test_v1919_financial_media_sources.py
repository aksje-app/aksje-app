from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import MagicMock, patch
import os
import tempfile

import news_intelligence
import news_source_registry


RSS_XML = b'''<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0"><channel><title>Test</title>
<item><title>Petrobras PETR4 wins major contract</title>
<description>Petrobras reports growth and a new contract.</description>
<link>https://example.test/petr4</link>
<pubDate>Sat, 25 Jul 2026 12:00:00 GMT</pubDate>
<category>Mercados</category></item>
<item><title>Conteudo Empiricus: PETR4 comprar ou vender?</title>
<description>Conteudo patrocinado com recomendacao.</description>
<link>https://example.test/sponsored</link>
<pubDate>Sat, 25 Jul 2026 11:00:00 GMT</pubDate>
<category>Conteudo Empiricus</category></item>
</channel></rss>'''


class _Response:
    status_code = 200
    encoding = "utf-8"
    content = RSS_XML

    def raise_for_status(self):
        return None


def _recent(title: str, publisher: str, url: str, article_type: str = "news"):
    return {
        "title": title,
        "summary": title,
        "publisher": publisher,
        "original_publisher": publisher,
        "url": url,
        "article_type": article_type,
        "published_at": datetime.now(timezone.utc).isoformat(),
    }


def test_registry_keeps_e24_and_adds_requested_markets():
    assert [row["id"] for row in news_source_registry.SOURCE_REGISTRY["Norge"]].count("e24") == 1
    assert {row["id"] for row in news_source_registry.SOURCE_REGISTRY["Sverige"]} == {"efn"}
    assert {row["id"] for row in news_source_registry.SOURCE_REGISTRY["Brasil"]} == {
        "infomoney", "money_times", "brazil_journal"
    }
    assert {row["id"] for row in news_source_registry.SOURCE_REGISTRY["USA"]} == {"cnbc"}


def test_yahoo_original_publisher_controls_quality():
    reuters = news_intelligence.normalize_articles([
        _recent("Reuters result", "Reuters", "https://finance.yahoo.com/news/x")
    ])[0]
    motley = news_intelligence.normalize_articles([
        _recent("Motley result", "Motley Fool", "https://finance.yahoo.com/news/y")
    ])[0]
    yahoo = news_intelligence.normalize_articles([
        _recent("Yahoo result", "Yahoo Finance", "https://finance.yahoo.com/news/z")
    ])[0]
    assert reuters["source_quality"] == 1.0
    assert yahoo["source_quality"] == 0.86
    assert motley["source_quality"] == 0.35


def test_sponsored_is_filtered_and_recommendation_is_downweighted():
    rows = [
        _recent("Conteudo Empiricus: paid idea", "Money Times", "https://moneytimes.com.br/a", "sponsored"),
        _recent("PETR4 comprar ou vender?", "Money Times", "https://moneytimes.com.br/b", "recommendation"),
        _recent("PETR4 reports earnings growth", "Money Times", "https://moneytimes.com.br/c", "news"),
    ]
    normalized = news_intelligence.normalize_articles(rows)
    assert len(normalized) == 2
    qualities = {row["article_type"]: row["source_quality"] for row in normalized}
    assert qualities["recommendation"] < qualities["news"]
    scored = news_intelligence.score_articles("PETR4.SA", rows)
    assert scored["filtered_sponsored_count"] == 1
    assert scored["recommendation_count"] == 1


def test_feed_is_downloaded_once_and_filtered_locally():
    fake_requests = MagicMock()
    fake_requests.get.return_value = _Response()
    spec = dict(news_source_registry.SOURCE_REGISTRY["Brasil"][0])
    with tempfile.TemporaryDirectory() as folder, \
         patch.object(news_source_registry, "FEED_CACHE_PATH", Path(folder) / "feed_cache.json"), \
         patch.dict("sys.modules", {"requests": fake_requests}):
        first, first_meta = news_source_registry.fetch_rss_source(spec, ["petr4"])
        second, second_meta = news_source_registry.fetch_rss_source(spec, ["vale3"])
    assert len(first) == 2
    assert second == []
    assert fake_requests.get.call_count == 1
    assert first_meta["cache_status"] == "MISS"
    assert second_meta["cache_status"] == "HIT"


def test_brazil_sources_are_auditable_in_search_log():
    article = _recent("Petrobras PETR4 wins contract", "InfoMoney", "https://infomoney.com.br/x")

    def fake_feed(spec, tokens):
        rows = [dict(article, source_role=spec["source_role"], collector_source=spec["label"])] if spec["id"] == "infomoney" else []
        return rows, {"cache_status": "HIT", "cache_age_seconds": 10, "feed_items_scanned": 20}

    with tempfile.TemporaryDirectory() as folder, \
         patch.object(news_intelligence, "CACHE_PATH", Path(folder) / "result_cache.json"), \
         patch.object(news_intelligence, "_fetch_yfinance", return_value=[]), \
         patch.object(news_intelligence, "fetch_rss_source", side_effect=fake_feed), \
         patch.dict(os.environ, {"NEWSAPI_KEY": ""}, clear=False):
        result = news_intelligence.fetch_news_intelligence(
            "PETR4.SA", "Petrobras", force_refresh=True, market="Brasil"
        )
    direct = [row for row in result["search_log"] if row.get("source_type") == "PRIMARY_OR_DIRECT_RSS"]
    assert [row["source_id"] for row in direct] == ["infomoney", "money_times", "brazil_journal"]
    assert direct[0]["status"] == "SUCCESS_WITH_RESULTS"
    assert direct[0]["cache_status"] == "HIT"
    assert result["source_breakdown"]["InfoMoney"] == 1
    assert result["configured_market_sources"] == [
        "InfoMoney Mercados RSS", "Money Times Mercados RSS", "Brazil Journal RSS"
    ]


def test_each_source_can_be_disabled_by_environment():
    with patch.dict(os.environ, {"NEWS_SOURCE_MONEY_TIMES_ENABLED": "false"}, clear=False):
        ids = {row["id"] for row in news_source_registry.source_specs("Brasil")}
    assert "money_times" not in ids
    assert "infomoney" in ids
