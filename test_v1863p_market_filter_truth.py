from security_metadata import filter_tickers_for_market, infer_security_listing, market_matches_filter


def test_market_filter_uses_ticker_listing_before_source_or_stale_market():
    stale_usa = {"ticker": "AAPL", "source": "Prognose", "market": "Norge"}
    oslo = {"ticker": "STB.OL", "source": "Prognose", "market": "USA"}
    stockholm = {"ticker": "VOLV-B.ST", "source": "Prognose", "market": "Norge"}

    assert infer_security_listing("AAPL", stale_usa)["market"] == "USA"
    assert infer_security_listing("STB.OL", oslo)["market"] == "Norge"
    assert infer_security_listing("VOLV-B.ST", stockholm)["market"] == "Sverige"

    assert market_matches_filter("AAPL", "Norge", stale_usa) is False
    assert market_matches_filter("STB.OL", "Norge", oslo) is True
    assert market_matches_filter("VOLV-B.ST", "Sverige", stockholm) is True

    assert filter_tickers_for_market(["AAPL", "STB.OL", "VOLV-B.ST"], "Norge") == ["STB.OL"]
