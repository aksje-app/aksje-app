from superfund_risk_cards import sorted_risk_positions,risk_counts,status_palette

def test_sorted_risk_cards_and_counts():
    rows=[{'name':'Normal','stop_status':'NORMAL','drop_from_peak_pct':0},
          {'name':'Warn','stop_status':'ADVARSEL','drop_from_peak_pct':2.2},
          {'name':'Near','stop_status':'NÆR STOPP','drop_from_peak_pct':2.82},
          {'name':'Stop','stop_status':'STOPP','drop_from_peak_pct':3.1},
          {'name':'Near2','stop_status':'NÆR STOPP','drop_from_peak_pct':2.5}]
    assert [x['name'] for x in sorted_risk_positions(rows)]==['Stop','Near','Near2','Warn','Normal']
    assert risk_counts(rows)=={'STOPP':1,'NÆR STOPP':2,'ADVARSEL':1,'NORMAL':1}
    assert len({status_palette(x)[0] for x in ('STOPP','NÆR STOPP','ADVARSEL','NORMAL')})==4

def test_empty_risk_cards():
    assert sorted_risk_positions([])==[]
    assert sum(risk_counts([]).values())==0
