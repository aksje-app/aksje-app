from datetime import datetime,timezone
from superfund_rotation_shadow import rotation_shadow

def row(id,score,category='ETF',currency='EUR'):
    return {'id':id,'name':id,'score':score,'category':category,'returns_currency':currency,'blocks':[],'price_at':'2026-10-14T00:00:00Z'}

def test_shadow_flags_only_old_competitive_position():
    t=datetime(2026,10,14,tzinfo=timezone.utc)
    rows=[row('held',1),row('new',3)]
    owned={'held':{'name':'held','bought_at':'2026-09-20T00:00:00+00:00'}}
    result=rotation_shadow(rows,owned,t)
    assert result['mode']=='SHADOW_ONLY'
    assert result['review_count']==0
    assert result['candidates'][0]['confirmations']==1
    assert result['candidates'][0]['status']=='CONFIRMING'
    assert result['candidates'][0]['held_days']==24

def test_shadow_not_triggered_for_recent_or_mismatched_currency():
    t=datetime(2026,10,14,tzinfo=timezone.utc)
    data=rotation_shadow([row('held',1),row('new',3,currency='NOK')],{'held':{'bought_at':'2026-10-10T00:00:00+00:00'}},t)
    assert data['review_count']==0

def test_three_distinct_days_required_for_review():
    rows=[row('held',1),row('new',3)]
    owned={'held':{'name':'held','bought_at':'2026-09-20T00:00:00+00:00','last_nok':100,'quantity':10}}
    prior={}
    from datetime import timedelta
    for day in range(3):
        for item in rows:item['price_at']=(datetime(2026,10,14,tzinfo=timezone.utc)+timedelta(days=day)).isoformat()
        result=rotation_shadow(rows,owned,datetime(2026,10,14,tzinfo=timezone.utc)+timedelta(days=day),previous=prior)
        prior={x['owned_id']:x for x in result['candidates']}
    assert result['review_count']==1
    assert result['candidates'][0]['estimated_roundtrip_cost_nok']==6

def test_repeated_scan_same_nav_does_not_confirm():
    rows=[row('held',1),row('new',3)]
    owned={'held':{'bought_at':'2026-09-20T00:00:00+00:00'}}
    first=rotation_shadow(rows,owned,datetime(2026,10,14,tzinfo=timezone.utc))
    previous={r['owned_id']:r for r in first['candidates']}
    again=rotation_shadow(rows,owned,datetime(2026,10,15,tzinfo=timezone.utc),previous=previous)
    assert again['candidates'][0]['confirmations']==1

def test_shadow_different_nav_dates_do_not_confirm():
    rows=[row('held',1),row('new',3)]
    rows[1]['price_at']='2026-10-13T00:00:00Z'
    owned={'held':{'bought_at':'2026-09-20T00:00:00+00:00'}}
    result=rotation_shadow(rows,owned,datetime(2026,10,14,tzinfo=timezone.utc))
    assert result['candidates'][0]['confirmations']==0

def test_old_nav_cannot_qualify_for_review():
    rows=[row('held',1),row('new',3)]
    for item in rows:item['price_at']='2026-09-01T00:00:00Z'
    owned={'held':{'bought_at':'2026-08-01T00:00:00+00:00'}}
    prior={'held':{'challenger_id':'new','confirmations':3,'evidence_date':'2026-08-31'}}
    result=rotation_shadow(rows,owned,datetime(2026,10,14,tzinfo=timezone.utc),previous=prior)
    assert result['review_count']==0
    assert result['candidates'][0]['status']=='STALE_NAV'
    assert result['candidates'][0]['confirmations']==0

def test_challenger_loses_advantage_resets_confirmations():
    rows=[row('held',2),row('new',1)]
    owned={'held':{'bought_at':'2026-08-01T00:00:00+00:00'}}
    prior={'held':{'challenger_id':'new','confirmations':3,'evidence_date':'2026-10-13'}}
    result=rotation_shadow(rows,owned,datetime(2026,10,14,tzinfo=timezone.utc),previous=prior)
    assert result['review_count']==0
    assert result['candidates'][0]['confirmations']==0
