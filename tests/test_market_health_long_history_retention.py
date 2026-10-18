from market_health_collector import HISTORY_LIMIT
from pathlib import Path

def test_history_retention_enough_for_multiyear_calibration():
    assert HISTORY_LIMIT >= 2500
    source=Path("market_health_collector.py").read_text(encoding="utf-8")
    assert 'timedelta(days=365*15)' in source
    assert '[-96:]' not in source
    assert '"observations": annual' in source
