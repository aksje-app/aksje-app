import superfund_engine as e
from test_superfund_v1 import item,step

def _held():
    base=item(day='2026-11-02',week=3)
    s,_=step(None,[base],'2026-11-02')
    s,_=step(s,[item(day='2026-11-03',week=3)],'2026-11-03')
    assert len(s['positions'])==1
    return s

def test_top15_queues_sell_without_confirmation_wait():
    s=_held()
    rows=[item(day='2026-11-04',week=2)]+[
        item('NO000000%04d:78'%i,day='2026-11-04',week=5-i*.01)
        for i in range(1,17)]
    s,_=step(s,rows,'2026-11-04')
    sells=[o for o in s['orders'] if o['side']=='SELL']
    assert len(sells)==1
    assert 'ROTATION_TOP15' in sells[0]['reason']
    assert len(s['positions'])==1  # never same-day fill
    s,_=step(s,[item(day='2026-11-05',week=2)],'2026-11-05')
    assert not s['positions']
    assert any(t['side']=='SELL' and t['execution']=='DELAYED_MODEL_ESTIMATE' for t in s['trades'])

def test_no_rotation_without_qualified_better_candidate():
    s=_held()
    rows=[item(day='2026-11-04',week=2)]+[
        item('NO000000%04d:78'%i,day='2026-11-04',week=5-i*.01,risk=7)
        for i in range(1,17)]
    s,_=step(s,rows,'2026-11-04')
    assert not [o for o in s['orders'] if o['side']=='SELL']

def test_buy_hold_never_rotates():
    s=_held()
    rows=[item(day='2026-11-04',week=2)]+[
        item('NO000000%04d:78'%i,day='2026-11-04',week=5-i*.01)
        for i in range(1,17)]
    s,_=e.cycle(s,rows,'2026-11-04T15:00:00+00:00',buy_hold=True)
    assert not [o for o in s['orders'] if o['side']=='SELL']
