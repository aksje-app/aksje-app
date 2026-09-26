from __future__ import annotations

from datetime import datetime, timezone

from quality_model_v2 import evaluate_shadow, summarize_shadow
from quality_valuation import evaluate_company


def _raw(roce_history, fcf_history):
    return {
        "ticker": "TEST.OL", "price": 100, "trailing_eps": 6,
        "annual_eps": [5, 5.5, 6, 5.2, 4.9],
        "financial_date": datetime.now(timezone.utc).isoformat(),
        "free_cash_flow": fcf_history[0], "free_cash_flow_history": fcf_history,
        "roce": roce_history[0], "roce_history": roce_history,
        "name": "Test", "country": "Norway", "currency": "NOK", "industry": "Industrials",
    }


def test_v11_improving_company_not_killed_by_historical_median():
    raw = _raw([.15, .09, .09, .10, .10], [10, 9, 8, 7, 6])
    row = evaluate_company(raw, as_of=datetime.now(timezone.utc))
    assert row["quality_state"] == "IMPROVING"
    assert row["group"] == "Kvalitetsselskap"
    assert row["roce_trend"] == "FORBEDRENDE"


def test_v11_flags_recent_deterioration():
    raw = _raw([.07, .18, .19, .20, .18], [10, 9, 8, 7, 6])
    row = evaluate_company(raw, as_of=datetime.now(timezone.utc))
    assert row["roce_trend"] == "SVEKKENDE"
    assert row["quality_state"] == "QUALITY_WEAKENING"


def test_v2_never_claims_moat_from_accounting_only():
    raw = _raw([.20, .19, .18, .21, .20], [10, 9, 8, 7, 6])
    active = evaluate_company(raw, as_of=datetime.now(timezone.utc))
    shadow = evaluate_shadow(raw, active)
    assert shadow["shadow_only"] is True
    assert shadow["production_effect"] is False
    assert shadow["moat_evidence"] == "NOT_DOCUMENTED"
    assert shadow["roic_minus_wacc_pct_points"] is None


def test_shadow_summary_is_observational():
    raw = _raw([.20, .19, .18], [10, 9, 8])
    active = evaluate_company(raw, as_of=datetime.now(timezone.utc))
    summary = summarize_shadow([evaluate_shadow(raw, active)])
    assert summary["shadow_only"] is True
    assert summary["production_effect"] is False
    assert summary["evaluated"] == 1
