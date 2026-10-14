from superfund_presentation import short_trend_from_observations, notification_batch

def test_short_trend_uses_distinct_observed_days():
    obs=[{'price_at':f'2026-10-{d:02d}T12:00:00Z','nok_price':p} for d,p in [(8,100),(9,105),(12,104),(13,102),(14,101)]]
    trend=short_trend_from_observations(obs)
    assert trend['last_1_sessions_pct'] == round((101/102-1)*100,2)
    assert trend['last_3_sessions_pct'] == round((101/105-1)*100,2)
    assert trend['recent_peak_distance_pct']<0

def test_missing_short_history_is_not_invented():
    assert short_trend_from_observations([])['last_1_sessions_pct'] is None
    event={'side':'STERK UKEUTVIKLING','id':'x','name':'Demo fund','returns':{'yield_1w':6},
           'short_trend':short_trend_from_observations([])}
    text,count=notification_batch([event])
    assert count==1
    assert 'ikke tilstrekkelig NAV-historikk' in text

def test_alert_calls_falling_trend_observation_not_trade_signal():
    obs=[{'price_at':f'2026-10-{d:02d}T12:00:00Z','nok_price':p} for d,p in [(8,110),(9,109),(12,107),(13,105),(14,102)]]
    event={'side':'STERK UKEUTVIKLING','id':'a','name':'Example','returns':{'yield_1w':6.0},
           'short_trend':short_trend_from_observations(obs)}
    message,count=notification_batch([event])
    assert count==1
    assert 'SVEKKET' in message
    assert 'ikke salgsordre' in message
    assert 'kursintervaller' in message
