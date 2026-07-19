from investment_pipeline import PipelineConfig, _sanitize_numeric_fields, run_pipeline


def test_numeric_sanitizer_handles_none_and_invalid():
    row, missing = _sanitize_numeric_fields({"ticker": "TEST", "beta": None, "pe": "bad", "volume": "1234"})
    assert row["beta"] is None
    assert row["pe"] is None
    assert row["volume"] == 1234.0
    assert set(missing) == {"beta", "pe"}


def test_pipeline_continues_when_candidate_has_none_fields(monkeypatch):
    import candidate_market_data
    monkeypatch.setattr(candidate_market_data, "enrich_candidate_rows", lambda rows, **kwargs: [
        {**rows[0], "data_fetch_status": "OK", "price": 100, "volume": 100000, "beta": None, "pe": None},
        {**rows[1], "data_fetch_status": "OK", "price": 50, "volume": 50000, "beta": "invalid", "pe": 18},
    ])
    cfg = PipelineConfig(market_scope="USA", scan_limit=2, deep_analysis_count=2, proposal_count=1)
    out = run_pipeline([{"ticker": "AAA", "market": "USA"}, {"ticker": "BBB", "market": "USA"}], cfg)
    assert out["summary"]["scanned"] == 2
    assert out["loader_diagnostics"]["scored_count"] == 2
