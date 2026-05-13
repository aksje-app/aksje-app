from app_version import get_app_version
from fund_etf_analyzer import analyze_fund_record, run_fund_etf_lab


def _fund_data(symbol):
    prices = [100, 101, 102, 104, 106, 108, 111, 113, 116, 118]
    return {"prices": prices, "expense_ratio": 0.03, "longName": f"{symbol} Test Fund"}


def _benchmark(_symbol):
    return {"prices": [100, 101, 101, 102, 103, 104, 105, 106, 107, 108]}


def test_v18550_version():
    assert get_app_version() == "v18.5.74"


def test_base_score_profile_is_separate_layer():
    row = analyze_fund_record("VOO", _fund_data("VOO"), fund_type="ETF", objective="Balansert", benchmark_data=_benchmark("SPY"))
    profile = row["base_score_profile"]
    assert row["base_score"] == profile["base_score"]
    assert profile["layer"] == "Layer 1"
    assert profile["model"] == "Base Fund Scoring"
    assert profile["explainable_ready"] is True
    assert set(profile["components"]) >= {"cost", "return", "risk", "benchmark", "data", "fit"}
    assert "Grunnscore" not in profile["summary"]


def test_run_lab_exposes_average_base_score():
    result = run_fund_etf_lab(["VOO", "BND", "HYG"], data_provider=_fund_data, benchmark_provider=_benchmark, max_funds=2)
    assert result["summary"]["selected_max"] == 2
    assert "best_base_score" in result["summary"]
    dq = result["decision_quality_summary"]
    assert dq["average_base_score"] is not None
    assert all("base_score" in row for row in dq["rows"])
