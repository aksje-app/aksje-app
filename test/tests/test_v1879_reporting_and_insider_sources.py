from pathlib import Path
import sys
import types

import international_insider_sources as sources
import market_intelligence as mi


def test_whole_currency_and_market_mapping():
    assert mi.format_whole_currency(1328909.4, "NOK") == "1 328 909 NOK"
    assert mi.format_whole_currency(-16474393, "USD") == "-16 474 393 USD"
    assert mi.market_currency("Sverige", "INVE-B.ST") == "SEK"
    assert mi.market_currency("", "STB.OL") == "NOK"


def test_risk_text_uses_reference_scale_not_percent():
    assert mi.format_risk(13.63) == "13.63 - LAV"
    assert mi.format_risk(41.44) == "41.44 - MODERAT"
    assert mi.format_risk(65) == "65 - HØY"


def test_newsapi_discovery_uses_header_and_stays_discovery_only(monkeypatch):
    captured = {}

    class Response:
        def raise_for_status(self):
            return None

        def json(self):
            return {"articles": [{
                "title": "Storebrand primary insider purchase", "url": "https://newsweb.oslobors.no/message/1",
                "publishedAt": "2026-07-21T08:00:00Z", "source": {"name": "NewsWeb"},
            }]}

    def fake_get(url, params, headers, timeout):
        captured.update({"url": url, "params": params, "headers": headers, "timeout": timeout})
        return Response()

    monkeypatch.setenv("NEWSAPI_KEY", "secret-test-key")
    sources._NEWS_CACHE.clear()
    monkeypatch.setitem(sys.modules, "requests", types.SimpleNamespace(get=fake_get))
    result = sources.discover_with_newsapi("STB.OL", "Storebrand", "Norge")
    assert result["status"] == "DISCOVERY_FOUND"
    assert result["articles"][0]["verification"] == "DISCOVERY_ONLY"
    assert result["articles"][0]["official_domain"] is True
    assert captured["headers"] == {"X-Api-Key": "secret-test-key"}
    assert "apiKey" not in captured["params"]


def test_market_coverage_distinguishes_verified_and_discovery():
    candidates = [
        {"market": "USA", "raw": {"insider_intelligence": {"coverage": "AVAILABLE", "official_source": "SEC"}}},
        {"market": "Norge", "raw": {"insider_intelligence": {"coverage": "DISCOVERY_ONLY", "official_source": "NewsWeb"}}},
        {"market": "Norge", "raw": {"insider_intelligence": {"coverage": "MISSING", "official_source": "NewsWeb"}}},
    ]
    rows = {row["market"]: row for row in mi.insider_coverage_by_market(candidates)}
    assert rows["USA"]["verified"] == 1
    assert rows["Norge"]["discovery"] == 1
    assert rows["Norge"]["missing"] == 1


def test_orchestrator_does_not_use_full_page_autorefresh():
    source = Path("autonomous_orchestrator_ui.py").read_text(encoding="utf-8")
    assert "st_autorefresh" not in source
    assert 'fragment(run_every="3s")' in source
