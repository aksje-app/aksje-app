from quality_market_prescreen import full_market_prescreen

def test_full_market_prescreen_examines_every_ticker_before_finalists(monkeypatch):
    import quality_market_prescreen as q
    calls = []
    def fake_enrich(tickers, **kwargs):
        calls.extend(tickers)
        return [{
            "ticker": ticker,
            "last_price": 100 + i,
            "trailing_pe": 15,
            "roe": 20 + i,
            "debt_to_equity": 20,
            "earnings_growth": i,
            "revenue_growth": i,
            "momentum_score": 50,
            "trend_score": 50,
            "data_fetch_status": "OK",
            "raw_fields_available": ["price", "fundamentals"],
        } for i, ticker in enumerate(tickers)]
    monkeypatch.setattr(q, "enrich_candidate_rows", fake_enrich)
    universe = [f"T{i:03d}.OL" for i in range(137)]
    result = full_market_prescreen(universe, finalist_limit=20, chunk_size=31)
    assert result["universe_count"] == 137
    assert result["examined_count"] == 137
    assert set(calls) == set(universe)
    assert len(result["finalists"]) == 20

def test_market_room_no_longer_slices_first_20():
    src = open("app.py", encoding="utf-8").read()
    ui = open("quality_valuation_ui.py", encoding="utf-8").read()
    assert "Maks aksjer i kvalitetsvurderingen" not in src
    assert "get_us_broad_tickers(limit=1600)" in src
    assert "list(market_tickers)[:MAX_SYMBOLS]" not in ui
    assert "full_market_prescreen(selected, MAX_SYMBOLS" in ui
