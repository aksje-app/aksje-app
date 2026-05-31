from security_metadata import filter_tickers_for_market, infer_security_listing, market_matches_filter


def test_market_filter_uses_ticker_listing_before_source_or_stale_market():
    stale_usa = {"ticker": "AAPL", "source": "Prognose", "market": "Norge"}
    oslo = {"ticker": "STB.OL", "source": "Prognose", "market": "USA"}
    stockholm = {"ticker": "VOLV-B.ST", "source": "Prognose", "market": "Norge"}
    helsinki = {"ticker": "NOKIA.HE", "source": "Prognose", "market": "USA"}
    copenhagen = {"ticker": "NOVO-B.CO", "source": "Prognose", "market": "USA"}
    brazil = {"ticker": "PETR4.SA", "source": "Prognose", "market": "USA"}

    assert infer_security_listing("AAPL", stale_usa)["market"] == "USA"
    assert infer_security_listing("STB.OL", oslo)["market"] == "Norge"
    assert infer_security_listing("VOLV-B.ST", stockholm)["market"] == "Sverige"
    assert infer_security_listing("NOKIA.HE", helsinki)["market"] == "Finland"
    assert infer_security_listing("NOVO-B.CO", copenhagen)["market"] == "Danmark"
    assert infer_security_listing("PETR4.SA", brazil)["market"] == "Brasil"

    assert market_matches_filter("AAPL", "Norge", stale_usa) is False
    assert market_matches_filter("STB.OL", "Norge", oslo) is True
    assert market_matches_filter("VOLV-B.ST", "Sverige", stockholm) is True
    assert market_matches_filter("NOKIA.HE", "Finland", helsinki) is True
    assert market_matches_filter("NOVO-B.CO", "Danmark", copenhagen) is True
    assert market_matches_filter("PETR4.SA", "Brasil", brazil) is True

    assert filter_tickers_for_market(["AAPL", "STB.OL", "VOLV-B.ST"], "Norge") == ["STB.OL"]
    assert filter_tickers_for_market(["AAPL", "NOKIA.HE", "NOVO-B.CO", "PETR4.SA"], "Norden") == ["NOKIA.HE", "NOVO-B.CO"]







