from insider_intelligence import score_transactions
from investment_pipeline import PipelineConfig


def test_clustered_buys_score_positive():
    rows = [
        {"Date": "2026-07-19", "Transaction": "Purchase", "Insider": "A", "Position": "CEO", "Shares": 10000, "Value": 1500000},
        {"Date": "2026-07-18", "Transaction": "Purchase", "Insider": "B", "Position": "CFO", "Shares": 5000, "Value": 800000},
    ]
    result = score_transactions("TEST", rows)
    assert result["score"] >= 70
    assert result["buy_count"] == 2
    assert result["coverage"] == "AVAILABLE"


def test_sales_score_negative():
    rows = [{"Date": "2026-07-19", "Transaction": "Sale", "Insider": "A", "Position": "CEO", "Shares": -10000, "Value": 1500000}]
    result = score_transactions("TEST", rows)
    assert result["score"] < 50
    assert result["sell_count"] == 1


def test_missing_is_neutral():
    result = score_transactions("TEST", [])
    assert result["score"] == 50
    assert result["coverage"] == "MISSING"


def test_config_normalizes_insider_weight():
    cfg = PipelineConfig().normalized()
    assert cfg.use_insider_intelligence is True
    assert "insider" in cfg.weights
    assert abs(sum(cfg.weights.values()) - 1.0) < 1e-9
