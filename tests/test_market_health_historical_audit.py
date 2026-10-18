from market_health_historical_audit import coverage_report
from market_health_ui import INDICATORS

def test_single_observation_never_qualifies_as_history():
    snapshot={"indicators":{"breadth":{"observations":[{"observed_at":"2026-10-16T00:00:00Z","value":55.152,"source":"Verified history"}]}}}
    result=coverage_report(snapshot)
    assert len(result["indicators"])==len(INDICATORS)==14
    assert result["indicators"]["breadth"]["dated_observations"]==1
    assert result["indicators"]["breadth"]["span_years"]==0
    assert result["calibration_approved"] is False
    assert result["trade_signals_enabled"] is False

def test_ten_year_span_alone_does_not_certify_quality():
    snapshot={"indicators":{"cape":{"observations":[
        {"observed_at":"2010-01-01T00:00:00Z","value":19,"source":"Source"},
        {"observed_at":"2026-01-01T00:00:00Z","value":30,"source":"Source"}]}}}
    result=coverage_report(snapshot)
    assert result["indicators"]["cape"]["minimum_span_met"] is True
    assert result["indicators"]["cape"]["historical_coverage_verified"] is False
    assert result["validated"] is False
