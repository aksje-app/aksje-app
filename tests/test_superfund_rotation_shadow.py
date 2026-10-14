from datetime import datetime,timezone
from superfund_rotation_shadow import rotation_shadow

def row(id,score,category='ETF',currency='EUR'):
    return {'id':id,'name':id,'score':score,'category':category,'returns_currency':currency,'blocks':[]}

def test_shadow_flags_only_old_competitive_position():
    t=datetime(2026,10,14,tzinfo=timezone.utc)
    rows=[row('held',1),row('new',3)]
    owned={'held':{'name':'held','bought_at':'2026-09-20T00:00:00+00:00'}}
    result=rotation_shadow(rows,owned,t)
    assert result['mode']=='SHADOW_ONLY'
    assert result['review_count']==1
    assert result['candidates'][0]['status']=='REVIEW_ONLY'
    assert result['candidates'][0]['held_days']==24

def test_shadow_not_triggered_for_recent_or_mismatched_currency():
    t=datetime(2026,10,14,tzinfo=timezone.utc)
    data=rotation_shadow([row('held',1),row('new',3,currency='NOK')],{'held':{'bought_at':'2026-10-10T00:00:00+00:00'}},t)
    assert data['review_count']==0
