from datetime import datetime,timedelta,timezone
from autonomy_stop_watch import inspect_positions,_valid_quote

NOW=datetime(2026,10,14,13,0,tzinfo=timezone.utc)
POS={'CMBTO.OL':{'average_price':199},'AAA':{'average_price':100}}

def test_detects_stop_and_reports_missing_held():
    r=inspect_positions(POS,{'CMBTO.OL':{'price':182.8,'observed_at':NOW.isoformat()}},5,NOW)
    assert r['mode']=='OBSERVATION_ONLY'
    assert r['checked']==2
    assert r['fresh_quotes']==1
    assert r['alerts'][0]['ticker']=='CMBTO.OL'
    assert 'AAA' in r['missing_or_stale_quotes']

def test_stale_or_future_price_not_used_for_stop():
    for offset in (timedelta(minutes=-36),timedelta(minutes=1)):
        assert _valid_quote(182.8,(NOW+offset).isoformat(),NOW) is None
    assert _valid_quote(182.8,'',NOW) is None

def test_no_trade_ledger_calls_in_read_only_monitor():
    from pathlib import Path
    code=Path('autonomy_stop_watch.py').read_text()
    assert '_sell(' not in code and '_record_trade(' not in code
    assert 'simulate_autonomy_cycle(' not in code
