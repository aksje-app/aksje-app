from superfund_rank_audit import owned_rank_audit

def row(id,score,blocks=None,currency='NOK'):
    return {'id':id,'isin':id,'name':id,'score':score,'category':'ETF',
            'returns_currency':currency,'blocks':blocks or []}

def test_owned_outside_top15_receives_review_not_trade():
    rows=[row('owned',1)]+[row(str(i),100-i) for i in range(20)]
    result=owned_rank_audit(rows,{'owned':{'name':'owned'}})
    assert result['mode']=='REVIEW_ONLY'
    assert result['positions'][0]['action']=='ROTATION_REVIEW'
    assert result['positions'][0]['group_rank']==21

def test_ineligible_owned_is_priority_review():
    rows=[row('owned',1,['SVAK_TREND'])]+[row(str(i),10-i) for i in range(3)]
    x=owned_rank_audit(rows,{'owned':{}})['positions'][0]
    assert x['action']=='PRIORITY_REVIEW'
    assert x['group_rank'] is None

def test_unlike_currency_does_not_count_as_comparable():
    rows=[row('owned',2,currency='NOK'),row('other',30,currency='EUR')]
    x=owned_rank_audit(rows,{'owned':{}})['positions'][0]
    assert x['better_comparable_qualified']==0
    assert x['group_rank']==1
