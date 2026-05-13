from app_version import get_app_version
from fund_etf_analyzer import analyze_fund_record, build_fund_explainability_profile


def _data(name="Demo ETF", expense=0.07):
    prices = [100 + i * 0.3 for i in range(260)]
    return {"name": name, "expense_ratio": expense, "prices": prices}


def test_v18551_version():
    assert get_app_version() == "v18.5.74"


def test_explainability_profile_added_to_fund_record():
    row = analyze_fund_record("VOO", _data(), fund_type="ETF", benchmark_data=_data("Benchmark", 0.05))
    profile = row["explainability_profile"]
    assert profile["layer"] == "Layer 2"
    assert profile["model"] == "Explainable Fund Intelligence"
    assert isinstance(profile["why_ranked_here"], list) and profile["why_ranked_here"]
    assert isinstance(profile["what_would_make_it_selected"], list) and profile["what_would_make_it_selected"]
    assert isinstance(profile["what_would_make_model_reject_it"], list) and profile["what_would_make_model_reject_it"]
    assert row["explainability_summary"] == profile["summary"]


def test_active_fund_explainability_requires_proof():
    row = analyze_fund_record("ACTIVE", _data("Active Fund", 1.2), fund_type="Aktivt fond", benchmark_data=_data("Benchmark", 0.05))
    profile = build_fund_explainability_profile(row)
    joined = " ".join(profile["what_would_make_it_selected"] + profile["what_would_make_model_reject_it"])
    assert "benchmark" in joined.lower() or "meravkastning" in joined.lower()
