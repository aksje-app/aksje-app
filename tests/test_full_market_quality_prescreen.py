from quality_market_prescreen import full_market_prescreen

def test_full_market_prescreen_examines_every_ticker_before_finalists(monkeypatch):
    import quality_market_prescreen as q
    calls = []
    def fake_enrich(rows, **kwargs):
        calls.extend(row["ticker"] for row in rows)
        return [{
            "ticker": row["ticker"],
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
        } for i, row in enumerate(rows)]
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


def test_prescreen_module_is_tracked_in_runtime_tree():
    import quality_market_prescreen
    assert callable(quality_market_prescreen.full_market_prescreen)

def test_failed_new_run_does_not_fall_back_to_stale_saved_result():
    src = open("quality_valuation_ui.py", encoding="utf-8").read()
    assert 'st.session_state.pop("qv_result", None)' in src
    assert "if result is None and not run_attempted:" in src


def test_prescreen_passes_mapping_rows_to_market_enrichment(monkeypatch):
    import quality_market_prescreen as q
    seen = []
    def fake_enrich(rows, **kwargs):
        assert rows
        assert all(isinstance(row, dict) for row in rows)
        assert all("ticker" in row for row in rows)
        seen.extend(row["ticker"] for row in rows)
        return [{
            "ticker": row["ticker"],
            "last_price": 100,
            "data_fetch_status": "OK",
            "raw_fields_available": ["last_price"],
        } for row in rows]
    monkeypatch.setattr(q, "enrich_candidate_rows", fake_enrich)
    universe = ["EQNR.OL", "DNB.OL", "NHY.OL"]
    result = q.full_market_prescreen(universe, finalist_limit=2, chunk_size=2)
    assert seen == universe
    assert result["examined_count"] == 3
    assert result["finalists"] == ["EQNR.OL", "DNB.OL"]
