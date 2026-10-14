from superfund_challengers import evaluate_challengers

def candidate(id,score,category='ETF',currency='EUR',blocks=None):
    return {'id':id,'name':id,'score':score,'category':category,
            'returns_currency':currency,'blocks':blocks or []}

def test_relevant_challenger_and_unqualified_suppressed():
    rows=[candidate('owned',1.0),candidate('better',3.0),
          candidate('weak',0.5),candidate('blocked',10,blocks=['NO_PRICE'])]
    result=evaluate_challengers(rows,{'owned':{'id':'owned'}})
    by_id={r['id']:r for r in result['rows']}
    assert by_id['better']['candidate'] and by_id['better']['outperforms_held']==1
    assert not by_id['weak']['candidate']
    assert 'blocked' not in by_id

def test_comparability_avoids_cross_currency_claims():
    result=evaluate_challengers([candidate('owned',2,currency='NOK'),
                                  candidate('other',4,currency='EUR')],{'owned':{}})
    row=next(r for r in result['rows'] if r['id']=='other')
    assert row['outperforms_held']==0 and row['same_group_held']==0

def test_no_repeat_ranking_without_prior_snapshot():
    r=evaluate_challengers([candidate('x',4)],{},previous={})
    assert r['rows'][0]['rank_gain'] is None
