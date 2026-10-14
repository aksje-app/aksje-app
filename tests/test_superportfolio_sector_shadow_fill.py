from portfolio_evidence import classification, stop_alert_text

def test_sector_fallback_is_labelled_not_fake_industry():
    x=classification({'ticker':'ATCO-B.ST','sector':'Industrials'})
    assert x['industry']=='Industrielt utstyr'
    assert x['classification_known']
    assert x['classification_source'].startswith('https://www.atlascopcogroup.com')

def test_unknown_stays_unknown_without_evidence():
    x=classification({'ticker':'XYZ','sector':'Ukjent'})
    assert x['industry']=='Ukjent' and not x['classification_known']

def test_stop_alert_displays_model_fill_separately():
    text=stop_alert_text([{'ticker':'RVTY','action':'SHADOW SELL UTFØRT',
        'current_price':152.96,'shadow_exit_price':152.96,
        'shadow_exit_at':'2026-10-14T17:50:16+00:00',
        'entry_price':153.60,'stop_price':151.91}])
    assert 'Siste kurs 152.96' in text
    assert 'Simulert salgskurs 152.96' in text
    assert '2026-10-14T17:50:16+00:00' in text
    assert 'ingen faktisk børsutførelse' in text

def test_known_ticker_metadata_fills_missing_provider_sector():
    x=classification({'ticker':'ATCO-B.ST','sector':'Ukjent'})
    assert x['industry']=='Sektor: Industrials'
    assert x['classification_source'].startswith('https://www.atlascopcogroup.com')

def test_verified_business_fallback_for_all_six_held_tickers():
    for ticker in ('AKVA.OL','SUBC.OL','HEXA-B.ST','LOOMIS.ST','CAKE','ATCO-B.ST'):
        x=classification({'ticker':ticker,'sector':'Ukjent'})
        assert x['industry']!='Ukjent'
        assert x['classification_source'].startswith('https://')
