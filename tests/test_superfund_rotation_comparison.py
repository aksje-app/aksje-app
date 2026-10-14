from superfund_rotation_comparison import update_rotation_comparisons

def fund(id,price,day):
    return {'id':id,'price':price,'nok_rate':1,'price_at':day+'T12:00:00Z'}

def test_rotation_comparison_tracks_net_difference_only_on_new_nav():
    shadow={'candidates':[{'owned_id':'a','challenger_id':'b','status':'CONFIRMING'}]}
    first=update_rotation_comparisons([fund('a',100,'2026-10-13'),fund('b',100,'2026-10-13')],shadow)
    assert first['pairs']['a|b']['status']=='BASELINE'
    repeated=update_rotation_comparisons([fund('a',100,'2026-10-13'),fund('b',100,'2026-10-13')],shadow,first['pairs'])
    assert repeated['pairs']['a|b']['observations']==1
    next_day=update_rotation_comparisons([fund('a',99,'2026-10-14'),fund('b',102,'2026-10-14')],shadow,repeated['pairs'])
    assert next_day['pairs']['a|b']['status']=='MEASURED'
    assert abs(next_day['pairs']['a|b']['net_excess_return_pct']-2.4)<0.001

def test_missing_observed_prices_never_claim_outperformance():
    shadow={'candidates':[{'owned_id':'a','challenger_id':'b','status':'REVIEW_ONLY'}]}
    result=update_rotation_comparisons([fund('a',100,'2026-10-13'),{'id':'b','price_at':'2026-10-13'}],shadow)
    assert result['pairs']['a|b']['status']=='AWAITING_MATCHED_NAV'

def test_mismatched_nav_dates_cannot_create_false_outperformance():
    shadow={'candidates':[{'owned_id':'a','challenger_id':'b','status':'CONFIRMING'}]}
    result=update_rotation_comparisons([fund('a',100,'2026-10-13'),fund('b',110,'2026-10-14')],shadow)
    assert result['pairs']['a|b']['status']=='AWAITING_MATCHED_NAV'
    assert result['measured_count']==0
