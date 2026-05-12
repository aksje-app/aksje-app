from auto_test_lab import estimate_auto_lab_run, run_auto_test_lab


def _provider(ticker, use_news=False):
    base = {
        "AAPL": 7.8,
        "MSFT": 7.2,
        "KO": 5.8,
    }.get(ticker, 6.0)
    return {
        "ticker": ticker,
        "score": base,
        "smart_score": base * 10,
        "risk": "Lav" if ticker != "KO" else "Middels",
        "ret_1m": 0.04,
        "ret_3m": 0.08,
        "ret_6m": 0.12,
        "score_parts": {"momentum": 0.72, "trend": 0.68},
    }


def test_estimate_auto_lab_budget_counts_tests_and_news():
    est = estimate_auto_lab_run(["AAPL", "MSFT", "AAPL"], test_mode="Normal", use_news=True, include_event=True)
    assert est["tickers"] == 2
    assert est["tests_per_ticker"] >= 6
    assert est["total_tests"] == est["tickers"] * est["tests_per_ticker"]
    assert est["news_calls"] == 2
    assert est["load_label"] in {"Lav", "Medium", "Høy"}


def test_run_auto_test_lab_emits_total_progress_events():
    events = []
    result = run_auto_test_lab(
        ["AAPL", "MSFT"],
        score_provider=_provider,
        event_risk_provider=lambda ticker, prices: {"alerts": [], "confidence_adjustment": 0},
        test_mode="Normal",
        progress_callback=events.append,
        max_candidates=2,
        combination_sizes=[2],
    )
    assert result["status"] == "ok"
    assert result["completed_tests"] == result["total_tests"]
    assert result["total_tests"] > 0
    assert events[0]["status"] == "starting"
    assert events[-1]["status"] == "done"
    assert any(e.get("ticker") == "AAPL" and e.get("test_name") for e in events)
    assert max(e.get("percent", 0) for e in events) == 100.0


def test_run_auto_test_lab_can_stop_safely_after_first_progress():
    events = []
    stop_after = {"n": 0}

    def should_stop():
        stop_after["n"] += 1
        return stop_after["n"] > 1

    result = run_auto_test_lab(
        ["AAPL", "MSFT", "NVDA"],
        score_provider=_provider,
        test_mode="Grundig",
        progress_callback=events.append,
        should_stop=should_stop,
        max_candidates=3,
    )
    assert result["status"] == "interrupted"
    assert result["interrupted"] is True
    assert result["completed_tests"] < result["total_tests"]
    assert any(e.get("status") == "interrupted" for e in events)
