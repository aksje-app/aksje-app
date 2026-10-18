from datetime import datetime, timezone
from market_health_calibration_gate import audit_snapshot

def test_complete_does_not_validate_or_activate():
    at="2026-10-16T20:00:00+00:00"
    from market_health_ui import INDICATORS
    data={"indicators":{k:{"value":1,"source":"test dated observation","observed_at":at} for k in INDICATORS},
          "composite":{"validated":False},"collection_status":{"source_schema":5}}
    result=audit_snapshot(data,now=datetime(2026,10,17,10,tzinfo=timezone.utc))
    assert result["present_count"]==14
    assert result["validated"] is False
    assert result["risk_score"] is None
    assert result["trade_signals_enabled"] is False

def test_missing_is_blocked():
    result=audit_snapshot({"indicators":{}},now=datetime(2026,10,18,tzinfo=timezone.utc))
    assert result["calibration_ready"] is False
    assert result["missing"]
