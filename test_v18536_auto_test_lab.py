from auto_test_lab import (
    compute_decision_quality,
    run_auto_test_lab,
    build_candidate_combinations,
    parse_ticker_list,
)


def _item(ticker="AAPL", score=7.8, ret_1m=0.03, ret_3m=0.08, vol=0.018, dd=-0.12):
    return {
        "ticker": ticker,
        "name": ticker,
        "score": score,
        "score_parts": {"momentum": 0.72, "trend": 0.70},
        "ret_1m": ret_1m,
        "ret_3m": ret_3m,
        "ret_6m": 0.18,
        "volatility": vol,
        "max_drawdown": dd,
        "market_cap": 1_000_000_000,
    }


def test_parse_ticker_list_dedupes_and_accepts_multiple_separators():
    assert parse_ticker_list("aapl, msft\nAAPL; nvda") == ["AAPL", "MSFT", "NVDA"]


def test_decision_quality_positive_candidate_is_high_or_medium():
    result = compute_decision_quality(
        _item(),
        event_info={"alerts": [], "confidence_adjustment": 0, "is_event_risk": False},
        learning_stats={"hit_rate": 0.64},
    )
    assert result.ticker == "AAPL"
    assert result.decision_quality >= 60
    assert result.grade in {"Høy", "Middels"}
    assert result.ai_score == 78.0


def test_decision_quality_event_risk_can_force_wait():
    result = compute_decision_quality(
        _item(score=8.5),
        event_info={
            "is_event_risk": True,
            "confidence_adjustment": -20,
            "alerts": [{"level": "red", "message": "Earnings i morgen"}, {"level": "red", "message": "Nyhetsrisiko"}],
        },
    )
    assert result.grade in {"Vent", "Lav", "Middels"}
    assert result.event_score < 50
    assert result.reasons_caution


def test_run_auto_test_lab_returns_best_single_and_combinations():
    data = {t: _item(t, score=s) for t, s in [("AAPL", 8.1), ("MSFT", 7.7), ("NVDA", 7.5), ("KO", 6.8)]}

    def provider(ticker, use_news):
        return data.get(ticker)

    result = run_auto_test_lab(["AAPL", "MSFT", "NVDA", "KO"], score_provider=provider, max_candidates=4, combination_sizes=[2, 3])
    assert result["status"] == "ok"
    assert result["analyzed"] == 4
    assert result["best_single"][0]["ticker"] == "AAPL"
    assert result["combinations"]


def test_build_candidate_combinations_ignores_wait_rows():
    rows = [
        {"ticker": "AAPL", "decision_quality": 75, "risk_score": 70, "event_score": 80, "grade": "Høy", "sector": "Tech"},
        {"ticker": "MSFT", "decision_quality": 72, "risk_score": 68, "event_score": 78, "grade": "Middels", "sector": "Tech"},
        {"ticker": "BAD", "decision_quality": 40, "risk_score": 20, "event_score": 20, "grade": "Vent", "sector": "Risk"},
    ]
    combos = build_candidate_combinations(rows, sizes=[2])
    assert combos
    assert "BAD" not in combos[0]["tickers"]
