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
        for i in range(2,18)]
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
        for i in range(2,18)]
    s,_=step(s,rows,'2026-11-04')
    assert not [o for o in s['orders'] if o['side']=='SELL']

def test_buy_hold_never_rotates():
    s=_held()
    rows=[item(day='2026-11-04',week=2)]+[
        item('NO000000%04d:78'%i,day='2026-11-04',week=5-i*.01)
        for i in range(2,18)]
    s,_=e.cycle(s,rows,'2026-11-04T15:00:00+00:00',buy_hold=True)
    assert not [o for o in s['orders'] if o['side']=='SELL']

def test_brazil_event_cannot_rotate_into_another_brazil_fund():
    s=_held()
    # Verify the country-risk gate itself also rejects a Brazilian challenger.
    from superfund_event_risk import related, active, brazil_weight
    a=item(day='2026-10-14')
    b=item('NO0000000002:78',day='2026-10-14')
    for r in (a,b):
        r['detail']['regions']=[{'exposureType':'BRAZIL','weight':100}]
    assert active(e.at('2026-10-14T15:00:00+00:00'))
    assert brazil_weight(a)[0]==1 and related(a,b)
