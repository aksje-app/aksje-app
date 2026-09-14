from datetime import datetime, timedelta, timezone
import super_portfolio as sp

def _candidate(ticker='AAA', *, price=100, score=90, risk=30, quality=90, market='USA', sector='Tech', ts=None, earnings=None, currency='USD'):
    raw={'last_price':price,'data_timestamp':ts,'price_timestamp':ts,'currency':currency}
    if earnings: raw['earnings_date']=earnings
    return {'ticker':ticker,'price':price,'investment_score':score,'risk_score':risk,'data_quality_score':quality,'market':market,'sector':sector,'raw':raw}

def test_data_freshness_classifies_fresh_stale_and_gap():
    now=datetime(2026,9,14,12,0,tzinfo=timezone.utc)
    fresh=sp.data_freshness(_candidate(ts=(now-timedelta(hours=3)).isoformat()),now=now)
    stale=sp.data_freshness(_candidate(ts=(now-timedelta(days=4)).isoformat()),now=now)
    gap=sp.data_freshness(_candidate(ts=None),now=now)
    assert fresh['status']=='FRESH' and fresh['icon']=='🟢'
    assert stale['status']=='STALE' and stale['icon'] in {'🟡','🟠'}
    assert gap['status']=='DATA GAP' and gap['icon']=='🔴'

def test_event_risk_surfaces_upcoming_earnings():
    now=datetime(2026,9,14,12,0,tzinfo=timezone.utc)
    row=sp.event_risk(_candidate(earnings='2026-09-16'),now=now)
    assert row['status']=='UPCOMING' and row['days_until']==2 and row['icon'] in {'🟡','🟠'}

def test_decision_confidence_penalizes_stale_data_and_disagreement():
    strong=sp.decision_confidence(data_quality=92,freshness_score=100,regime_fit=88,score_spread=5,correlation_available=True)
    weak=sp.decision_confidence(data_quality=60,freshness_score=40,regime_fit=45,score_spread=30,correlation_available=False)
    assert strong['score']>weak['score'] and strong['icon']=='🟢' and weak['score']<70

def test_turnover_costs_estimate_change_cost_and_after_cost_return():
    changes=[{'action':'BUY','ticker':'AAA','from_pct':0,'to_pct':10},{'action':'REDUCE','ticker':'BBB','from_pct':15,'to_pct':10}]
    result=sp.turnover_cost_summary(changes,portfolio_value=1_000_000,gross_return_pct=2.0,cost_bps=10)
    assert result['turnover_pct']==15.0 and result['estimated_cost']==150.0 and result['net_return_pct']<2.0

def test_stress_radar_computes_market_sector_and_fx_scenarios():
    positions=[{'ticker':'AAA','market':'USA','sector':'Technology','currency':'USD','target_weight_pct':60},{'ticker':'BBB','market':'Norway','sector':'Shipping','currency':'NOK','target_weight_pct':40}]
    by={row['key']:row for row in sp.stress_radar(positions)}
    assert by['usa_-10']['estimated_portfolio_impact_pct']==-6.0
    assert by['shipping_-30']['estimated_portfolio_impact_pct']==-12.0
    assert by['usd_-10']['estimated_portfolio_impact_pct']==-6.0

def test_benchmark_summary_supports_index_and_manual_aurora():
    state=sp.default_state(); state['benchmark']={'index':{'label':'S&P 500','return_pct':4.5,'status':'AVAILABLE'},'aurora':{'label':'Aurora','return_pct':3.0,'status':'MANUAL'}}
    result=sp.benchmark_summary(state,portfolio_return_pct=6.0)
    assert result['index']['alpha_pct']==1.5 and result['aurora']['alpha_pct']==3.0

def test_resource_health_uses_memory_and_storage_reports(monkeypatch):
    monkeypatch.setattr(sp,'_memory_snapshot',lambda:{'process_rss_mb':250.0,'cgroup_memory_used_pct':62.0,'cgroup_memory_current_mb':320.0,'cgroup_memory_limit_mb':512.0})
    monkeypatch.setattr(sp,'_storage_usage_report',lambda:{'database_bytes':2_000_000_000,'capacity_bytes':5_000_000_000,'capacity_pct':40.0,'capacity_state':'OK'})
    health=sp.resource_health()
    assert health['status']=='OK' and health['icon']=='🟢' and health['memory_used_pct']==62.0 and health['db_used_pct']==40.0

def test_master_checklist_marks_rc16_32d_scope_done():
    rows={row['key']:row for row in sp.master_checklist()}
    expected={'external_benchmark','stress_radar','resource_panel','data_freshness','turnover_costs','event_risk','decision_confidence'}
    assert expected.issubset(rows)
    assert all(rows[key]['status']=='DONE' for key in expected)

def test_evaluate_persists_freshness_event_confidence_stress_and_costs(monkeypatch):
    now=datetime(2026,9,14,12,0,tzinfo=timezone.utc)
    cfg=sp.SuperPortfolioConfig(target_positions=2)
    state=sp.default_state(cfg)
    monkeypatch.setattr(sp,'load_state',lambda:state)
    pipeline={'run_id':'R32D','candidates':[
        _candidate('AAA',sector='Technology',ts=(now-timedelta(hours=1)).isoformat(),earnings='2026-09-16'),
        _candidate('BBB',sector='Shipping',market='Norway',currency='NOK',ts=(now-timedelta(hours=2)).isoformat()),
    ]}
    result=sp.evaluate(pipeline=pipeline,persist=False,now=now,rebalance_policy='FORCE')
    new=result['state']
    assert new['stress_radar']
    assert new['decision_confidence']['score']>0
    assert 'turnover_pct' in new['turnover_costs']
    assert new['positions']['AAA']['data_freshness']['status']=='FRESH'
    assert new['positions']['AAA']['event_risk']['status']=='UPCOMING'

def test_ui_contract_exposes_all_rc16_32d_panels():
    source=open('pages/super_portfolio.py',encoding='utf-8').read()
    for text in ('📊 Benchmark','🧯 Stress Radar','🖥️ Ressurser','🕒 Data Freshness','💸 Turnover','📅 Event Risk','🧠 Decision Confidence'):
        assert text in source


def test_scheduled_cycle_refreshes_index_benchmark(monkeypatch):
    state=sp.default_state(); state['last_scheduled_source_run_id']='OLD'
    pipeline={'run_id':'NEW','candidates':[]}
    monkeypatch.setattr(sp,'load_state',lambda:state)
    monkeypatch.setattr(sp,'get_or_build_super_portfolio_market_pipeline',lambda **kwargs:pipeline)
    monkeypatch.setattr(sp,'evaluate',lambda **kwargs:{'state':{**state,'positions':{}},'changes':[],'stop_alerts':[],'rebalance_due':False})
    refreshed=[]
    monkeypatch.setattr(sp,'refresh_index_benchmark',lambda state=None: refreshed.append(True) or {'status':'AVAILABLE','return_pct':1.0})
    monkeypatch.setattr(sp,'resource_health',lambda:{'status':'OK','icon':'🟢'})
    monkeypatch.setattr(sp,'save_state',lambda value: state.update(value) or value)
    monkeypatch.setattr(sp,'append_event',lambda *a,**k:None)
    result=sp.run_scheduled_shadow_cycle()
    assert result['state']=='COMPLETED'
    assert refreshed

def test_pdf_contains_rc16_32d_intelligence_sections():
    import io
    from pypdf import PdfReader
    state=sp.default_state()
    state['positions']={'AAA':{'ticker':'AAA','target_weight_pct':100,'pnl_pct':5,'portfolio_score':90,'rank':1,'rank_arrow':'↑','stop_status':'SAFE','stop_icon':'🟢','stop_pressure':'LOW','stop_pressure_icon':'🟢','stop_direction_arrow':'→'}}
    state['portfolio_health']={'score':85,'icon':'🟢','label':'STRONG','components':{}}
    state['benchmark']={'index':{'label':'S&P 500','return_pct':2.0,'status':'AVAILABLE'},'aurora':{'label':'Aurora','return_pct':1.0,'status':'MANUAL'}}
    state['stress_radar']=[{'label':'USA -10%','icon':'🟠','exposure_pct':100,'estimated_portfolio_impact_pct':-10}]
    state['turnover_costs']={'turnover_pct':10,'estimated_cost':100,'net_return_pct':4.9}
    state['decision_confidence']={'score':88,'icon':'🟢','label':'HIGH'}
    text='\n'.join(page.extract_text() or '' for page in PdfReader(io.BytesIO(sp.build_pdf(state))).pages)
    assert 'Benchmark' in text
    assert 'Stress Radar' in text
    assert 'Decision Confidence' in text
    assert 'Turnover' in text
