from __future__ import annotations
from datetime import datetime, timezone
from quality_model_v2 import evaluate_shadow
from quality_v2_benchmark import compare_reference

def _base(**extra):
    row={"ticker":"TEST.OL","roce_history":[.16,.15,.14,.13],"free_cash_flow_history":[10,9,8,7],
         "annual_eps":[5,4.5,4,3.5],"operating_margin_history":[.15,.14,.13,.12]}
    row.update(extra); return row

def test_financial_sector_uses_roe_not_industrial_roce():
    raw=_base(is_financial=True, sector="Financial Services", roce_history=[], roe_history=[.17,.16,.15,.14])
    out=evaluate_shadow(raw,{"ticker":"BANK.OL","quality_state":"INSUFFICIENT","group":"Ufullstendig"})
    assert out["sector_policy"]=="FINANCIAL_ROE"
    assert out["quality_band"]=="STRONG"
    assert out["shadow_only"] and not out["production_effect"]

def test_cyclical_model_requires_multiperiod_evidence():
    raw=_base(industry="Oil & Gas", operating_margin_history=[.30], free_cash_flow_history=[10])
    out=evaluate_shadow(raw,{"ticker":"OIL.OL","quality_state":"QUALITY","group":"Kvalitetsselskap"})
    assert out["cyclical"] is True
    assert out["cyclical_normalization"]=="NOT_DOCUMENTED"

def test_benchmark_never_has_production_effect():
    out=compare_reference([{"ticker":"ATCO-A.ST","quality_band":"STRONG"}])
    assert out["production_effect"] is False
    assert out["matched_count"]==1
