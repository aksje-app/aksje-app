import event_risk_engine as ere
from forecast_engine import build_forecast


def test_event_risk_detects_earnings_news_volatility_and_adjusts_confidence():
    original_earnings = ere._earnings_signal
    original_news = ere._news_signal
    try:
        ere._earnings_signal = lambda ticker: {
            "available": True,
            "active": True,
            "days_until": 2,
            "date": "2026-05-12",
        }
        ere._news_signal = lambda ticker, limit=8: {
            "available": True,
            "keyword_hits": 3,
            "hit_titles": ["Probe and downgrade"],
            "article_count": 1,
        }
        prices = []
        value = 100.0
        # Alternating high moves creates elevated realized volatility.
        for idx in range(45):
            value *= 1.055 if idx % 2 == 0 else 0.945
            prices.append(value)

        info = ere.detect_event_risk("AAPL", prices, horizon="1m", include_news=True)
        categories = {a.get("category") for a in info["alerts"]}

        assert info["is_event_risk"] is True
        assert info["confidence_adjustment"] < 0
        assert "earnings_event" in categories
        assert "news_risk" in categories
        assert any(c in categories for c in {"high_volatility", "elevated_volatility"})

        summary = ere.summarize_event_risk(info)
        assert "Hendelsesrisiko nær" in summary

        breakdown = ere.event_risk_confidence_breakdown(
            base_confidence=70,
            event_info=info,
            learning_adjustment=4,
        )
        assert breakdown["base_confidence"] == 70
        assert breakdown["event_adjustment"] == info["confidence_adjustment"]
        assert breakdown["adjusted_confidence"] <= 74
    finally:
        ere._earnings_signal = original_earnings
        ere._news_signal = original_news


def test_forecast_confidence_breakdown_has_no_hidden_double_penalty():
    prices = [100 + i * 0.6 for i in range(80)]
    baseline = build_forecast("AAPL", prices, "1m", ai_score=60, sentiment_score=0.1)
    adjusted = build_forecast(
        "AAPL",
        prices,
        "1m",
        ai_score=60,
        sentiment_score=0.1,
        event_risk=True,
        event_confidence_adjustment=-12,
        learned_confidence_adjustment=3,
        event_risk_summary="Hendelsesrisiko nær: test",
    )

    assert adjusted.summary.confidence_base == baseline.summary.confidence
    assert adjusted.summary.confidence_adjustment_event == -12
    assert adjusted.summary.confidence_adjustment_learning == 3
    assert adjusted.summary.confidence_adjustment_total == -9
    assert adjusted.summary.confidence == max(5, min(95, baseline.summary.confidence - 9))
    assert adjusted.summary.event_risk is True
    assert "Hendelsesrisiko nær" in adjusted.summary.event_risk_summary
