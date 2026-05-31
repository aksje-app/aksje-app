from analysis import apply_insider_adjustment, score_from_metrics
from auto_test_lab import compute_decision_quality
from signal_engine import calculate_signal_intelligence
from universe_engine import candidate_from_score_item


METRICS = {
    "ret_6m": 0.12,
    "ret_3m": 0.06,
    "ret_1m": 0.02,
    "trend_50": 0.04,
    "trend_200": 0.08,
    "volatility": 0.018,
    "max_drawdown": -0.12,
    "downside_vol": 0.014,
    "volume_trend_score": 0.55,
}


def test_insider_score_adjusts_base_score_without_punishing_missing_data():
    neutral, neutral_parts = score_from_metrics(METRICS, sentiment=0.5, insider_score=0.5)
    positive, positive_parts = score_from_metrics(METRICS, sentiment=0.5, insider_score=0.8)
    negative, negative_parts = score_from_metrics(METRICS, sentiment=0.5, insider_score=0.2)

    assert positive > neutral > negative
    assert neutral_parts["insider"] == 0.5
    assert positive_parts["insider"] == 0.8
    assert negative_parts["insider"] == 0.2


def test_apply_insider_adjustment_keeps_explainable_fields():
    item = {"ticker": "TEST", "score": 7.0, "score_parts": {"momentum": 0.7}}
    adjusted = apply_insider_adjustment(item, insider={"score": 0.75, "label": "Positivt insiderbilde", "transactions": 2})

    assert adjusted["score"] > item["score"]
    assert adjusted["base_score_before_insider"] == 7.0
    assert adjusted["insider_score"] == 0.75
    assert adjusted["score_parts"]["insider"] == 0.75


def test_signal_engine_uses_insider_from_score_item():
    base_item = {"ticker": "TEST", "score": 6.8}
    positive_item = {"ticker": "TEST", "score": 6.8, "insider_score": 0.85}

    base = calculate_signal_intelligence(base_item, {"rsi": 55, "macd_bullish": True, "trend": "up"})
    positive = calculate_signal_intelligence(positive_item, {"rsi": 55, "macd_bullish": True, "trend": "up"})

    assert positive["final_score"] > base["final_score"]
    assert any("Insider" in reason for reason in positive["reasons"])


def test_universe_and_auto_lab_preserve_insider_metadata():
    item = {
        "ticker": "TEST",
        "name": "Test ASA",
        "score": 7.2,
        "score_parts": {"momentum": 0.75, "trend": 0.7, "insider": 0.8},
        "ret_1m": 0.03,
        "ret_3m": 0.08,
        "ret_6m": 0.14,
        "volatility": 0.018,
        "max_drawdown": -0.12,
        "insider_score": 0.8,
        "insider_label": "Positivt insiderbilde",
    }

    candidate = candidate_from_score_item("TEST", item)
    quality = compute_decision_quality(item)

    assert candidate.insider_score == 80.0
    assert "insiderbilde" in candidate.reason
    assert quality.insider_score == 80.0







