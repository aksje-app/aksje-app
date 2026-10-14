from datetime import datetime, timezone
from portfolio_evidence import ownership_duration,stop_alert_text

def test_ownership_days_from_purchase_date():
    now=datetime(2026,10,14,tzinfo=timezone.utc)
    assert ownership_duration('2026-10-01T10:00:00Z',now)=='13 kalenderdager'
    assert ownership_duration(None,now).startswith('ukjent')
    assert ownership_duration('bad',now).startswith('ukjent')

def test_stop_alert_shows_held_duration_when_present():
    msg=stop_alert_text([{'ticker':'DEMO','entry_date':'2026-10-01','entry_price':100,'current_price':101,'stop_price':98,'to':'WATCH'}])
    assert 'Eid i ' in msg
    assert 'Kjøpskurs 100.00' in msg
