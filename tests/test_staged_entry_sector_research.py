from staged_entry_sector_research import Policy, next_target, permitted_weight, can_use_historical_snapshot
import pytest

def test_staging_never_automatic_without_confirmation():
    p=Policy()
    assert next_target(p,20,confirmed=False)==1.0
    assert [next_target(p,x,confirmed=True) for x in (0,3,7,15)]==[1.,2.,3.5,5.]

def test_concentration_caps_and_cash():
    p=Policy()
    book=[{"ticker":"A","sector":"Technology","industry":"Software","weight_pct":12.},
          {"ticker":"B","sector":"Technology","industry":"Hardware","weight_pct":10.}]
    assert permitted_weight(p,book,ticker="C",sector="Technology",industry="Software",target_pct=5)["allowed_pct"]==3
    assert permitted_weight(p,book,ticker="C",sector="Technology",industry="Software",target_pct=5,available_cash_pct=1)["allowed_pct"]==1

def test_unknown_classification_blocks_purchase():
    assert permitted_weight(Policy(),[],ticker="A",sector="",industry="",target_pct=1)["reason"]=="MISSING_AS_OF_CLASSIFICATION"

def test_point_in_time_required():
    assert not can_use_historical_snapshot({"as_of":"2020-01-01","candidates":[{"ticker":"A","sector":"Technology"}]})
    assert can_use_historical_snapshot({"as_of":"2020-01-01","candidates":[{"ticker":"A","signal_as_of":"2020-01-01","sector_as_of":"2020-01-01","industry_as_of":"2020-01-01","sector":"Tech","industry":"Software"}]})

def test_invalid_caps_rejected():
    with pytest.raises(ValueError):
        next_target(Policy(industry_limit_pct=40,sector_limit_pct=25),0,confirmed=True)
