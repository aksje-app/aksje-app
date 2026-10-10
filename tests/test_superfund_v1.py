from copy import deepcopy
from datetime import datetime, timezone
import json
import multiprocessing
import pytest

import superfund_engine as engine
import superfund_runtime as runtime
from superfund_data import embedded, normalize, nok_rate
from services.storage_service import StorageService
REAL_DELIVERY = runtime.deliver_pending


def item(key='NO0000000001:78',price=100,day='2026-10-05',week=2,category='Global',**extra):
    return {'id':key,'isin':key.split(':')[0],'name':key,'kind':'fond','currency':'NOK',
        'price':price,'price_at':day+'T00:00:00+00:00','observed_at':day+'T12:00:00+00:00',
        'nok_rate':1,'category':category,'asset':'Aksje','risk':4,'cost_pct':0.2,
        'tradable':True,'complex':False,'distribution':'Akkumuleres i fondet',
        'returns':{'yield_1w':week,'yield_1m':3,'yield_3m':5},'returns_currency':'NOK',
        'detail':{'trading':{'buyFrequency':'DAILY','sellFrequency':'DAILY',
            'nextBuyAt':'2026-10-06T09:00:00+00:00','nextSellAt':'2026-10-06T09:00:00+00:00'}},**extra}


def step(state,items,day='2026-10-05',p=None):
    return engine.cycle(state,items,day+'T15:00:00+00:00',p)


def test_fund_fill_waits_for_later_nav_and_preserves_cash():
    original=engine.initial();s,r=step(original,[item()])
    assert not s['positions'] and len(s['orders'])==1
    assert original==engine.initial()
    repeat,_=step(s,[item()]);assert repeat==s
    s,_=step(s,[item(price=105,day='2026-10-06')],'2026-10-06')
    assert len(s['positions'])==1 and not s['orders']
    pos=next(iter(s['positions'].values()))
    assert pos['entry_nok']==105 and pos['rank_at_buy']==1
    assert s['cash']+pos['cost_nok']==pytest.approx(s['initial_capital'])
    assert pos['quantity']*105<pos['cost_nok']


def test_refill_scans_past_blocked_and_duplicate_listings():
    rows=[item(week=50,risk=7),item('NO0000000002:78',week=4),item('NO0000000002:4',week=3)]
    s,r=step(None,rows)
    assert [o['isin'] for o in s['orders']]==['NO0000000002']


def test_category_limits_and_cash_reserve():
    rows=[item('NO00000000%02d:78'%n,category='One',week=5-n*0.1) for n in range(1,10)]
    s,_=step(None,rows)
    assert sum(o['allocation'] for o in s['orders'])<=300000
    assert len(s['orders'])<=8


def test_future_stale_missing_and_complex_blocked():
    for x in [item(day='2026-10-07'),item(day='2026-09-01'),item(nok_rate=None),item(complex=True),item(detail={})]:
        s,_=step(None,[x]);assert not s['orders']


def test_weakening_before_execution_cancels_buy():
    s,_=step(None,[item()]);s,r=step(s,[item(day='2026-10-06',week=-2)],'2026-10-06')
    assert not s['positions'] and r['changes'][0]['side']=='CANCEL'


def test_profit_floor_and_delayed_exit_cooldown():
    s,_=step(None,[item()]);s,_=step(s,[item(day='2026-10-06')],'2026-10-06')
    s,_=step(s,[item(day='2026-10-07',price=110)],'2026-10-07')
    pos=next(iter(s['positions'].values()));assert pos['floor_nok']==pytest.approx(105.5)
    s,_=step(s,[item(day='2026-10-08',price=104)],'2026-10-08');assert s['orders'][0]['side']=='SELL'
    s,r=step(s,[item(day='2026-10-09',price=103)],'2026-10-09')
    assert not s['positions'] and not s['orders'] and s['trades'][-1]['side']=='SELL'
    assert s['trades'][-1]['price_nok']==103


def test_fx_uses_prior_day_and_rejects_missing_or_stale():
    fx={'days':{'2026-10-05':{'NOK':10,'EUR':1,'USD':2},'2026-10-07':{'NOK':12,'USD':2}}}
    assert nok_rate('USD','2026-10-06',fx)==5
    assert nok_rate('USD','2026-10-04',fx) is None
    assert nok_rate('USD','2026-10-20',fx) is None


def test_parser_schema_failure_and_real_fixture_shape():
    assert embedded('window.__initialState__="{\\"a\\":1}";', '__initialState__')=={'a':1}
    with pytest.raises(ValueError):embedded('signin', '__initialState__')
    row={'instrument_info':{'isin':'NO0000000001','name':'Fund','currency':'NOK','is_tradable':True},
         'price_info':{'last':{'price':100},'tick_timestamp':1791158400000},'fund_info':{'fund_type':'Aksje'}}
    assert normalize(row,'fond','2026-10-05T12:00:00+00:00')['price']==100


@pytest.fixture
def local(monkeypatch,tmp_path):
    store=StorageService(base_dir=tmp_path,mode='local',database_url='')
    monkeypatch.setattr(runtime,'storage',lambda:store)
    monkeypatch.setenv('APP_RUNTIME_ROOT',str(tmp_path))
    monkeypatch.delenv('DATABASE_URL',raising=False)
    monkeypatch.setattr(runtime,'optional_capacity',lambda:{'ready':True})
    monkeypatch.setattr(runtime,'deliver_pending',lambda:None)
    return store


def raw_row(isin):
    return {'instrument_info':{'isin':isin,'name':isin,'currency':'NOK','is_tradable':True},
            'price_info':{'last':{'price':100},'tick_timestamp':1791158400000},
            'historical_returns_info':{'yield_1w':2,'yield_1m':3,'yield_3m':5},
            'fund_info':{'fund_type':'Aksje','fund_category':'Global','fund_raw_risk':4,'fund_total_fee':0.2}}


def test_batch_checkpoint_restart_and_complete_gate(local):
    calls=[]
    def provider(kind,page):
        calls.append((kind,page))
        return {'kind':kind,'page':page,'total':200,'rows':[raw_row('NO000000000'+str(page))],'url':'source'}
    r=runtime.run_batch(1,page_provider=provider,fx_provider=lambda:{'days':{}},enrich=False)
    assert r['state']=='PARTIAL' and not runtime.snapshot()
    r=runtime.run_batch(3,page_provider=provider,fx_provider=lambda:{'days':{}},enrich=False)
    assert calls==[('fond',1),('fond',2),('etf',1),('etf',2)]
    assert r['state']=='COMPLETED' and runtime.snapshot()['coverage']['complete']


def test_failed_page_keeps_last_snapshot_and_cursor(local):
    old={'model':{'cash':123},'report':{'url':'old'}};runtime.write('snapshot.json',old)
    def bad(*a):raise ValueError('provider unavailable')
    assert runtime.run_batch(page_provider=bad,fx_provider=lambda:{'days':{}},enrich=False)['state']=='FAILED'
    assert runtime.snapshot()==old


def test_request_dedup_and_parameter_audit_rollback(local):
    assert runtime.request_scan()==runtime.request_scan()
    runtime.save_parameters({'stop_pct':5},'test')
    assert runtime.config()['stop_pct']==5
    runtime.rollback('test');assert runtime.config()['stop_pct']==6
    assert len(runtime.read('parameter_audit.json')['history'])==2
    with pytest.raises(ValueError):runtime.save_parameters({'max_position_pct':99})


def _child_lane(queue):
    from resource_coordinator import execution_lane
    with execution_lane('child') as acquired:queue.put(acquired)


def test_lane_serializes_processes_and_releases_after_exception(local):
    from resource_coordinator import execution_lane
    ctx=multiprocessing.get_context('spawn');q=ctx.Queue()
    with execution_lane('parent') as acquired:
        assert acquired
        child=ctx.Process(target=_child_lane,args=(q,));child.start();child.join(5)
        assert q.get(timeout=2) is False
        with execution_lane('nested') as nested:assert nested
    child=ctx.Process(target=_child_lane,args=(q,));child.start();child.join(5)
    assert q.get(timeout=2) is True
    with pytest.raises(ValueError):
        with execution_lane('error'):raise ValueError()
    with execution_lane('after') as acquired:assert acquired


def test_pdf_workbook_csv_share_snapshot_and_route():
    from superfund_reports import pdf_bytes,csv_bytes,xlsx_bytes
    from ui_library.shell import canonical_shell_route,MOBILE_ROUTES
    s={'at':'2026-10-05','model':engine.initial(),'parameters':engine.DEFAULTS}
    assert pdf_bytes(s).startswith(b'%PDF')
    assert xlsx_bytes(s).startswith(b'PK')
    assert b'ISIN' in csv_bytes(s)
    assert canonical_shell_route('superfund')=='superfund'
    assert any(r.slug=='superfund' for r in MOBILE_ROUTES)


def test_reference_is_buy_hold_with_matched_capital(local):
    from superfund_learning import forward_evidence,equity
    p=engine.DEFAULTS;ref=item(name='Nordnet Global Indeks')
    model=engine.initial();first=forward_evidence({},model,{},[ref],'2026-10-05T15:00:00+00:00',p)
    assert first['reference_id']==ref['id']
    second=forward_evidence({'learning':first},model,{},[item(name='Nordnet Global Indeks',day='2026-10-06')],'2026-10-06T15:00:00+00:00',p)
    baseline=second['baseline'];pos=next(iter(baseline['positions'].values()))
    assert pos['cost_nok']==pytest.approx(900000)
    assert baseline['cash']==pytest.approx(100000)
    assert 'paired_start' in second


def test_learning_approval_one_click_atomic_and_stale_guard(local):
    from superfund_learning import decide_proposal
    proposal={'id':'p1','state':'WAITING_APPROVAL','parameter':'min_week_pct','current':1.0,'proposed':0.5}
    runtime.write('snapshot.json',{'learning':{'proposal':proposal},'model':{'cash':123}})
    assert decide_proposal('p1',True)['state']=='IMPLEMENTED'
    assert runtime.config()['min_week_pct']==0.5
    decide_proposal('p1',True)
    assert len(runtime.read('parameter_audit.json')['history'])==1
    assert runtime.snapshot()['model']['cash']==123
    runtime.write('snapshot.json',{'learning':{'proposal':{**proposal,'id':'p2'}}})
    with pytest.raises(ValueError):decide_proposal('p2',True)


def test_historical_insufficient_and_future_leakage_rejected():
    from superfund_learning import historical_experiment
    assert historical_experiment([])['state']=='INSUFFICIENT_HISTORY'
    from datetime import timedelta
    start=datetime(2026,1,1,tzinfo=timezone.utc);frames=[]
    for day in range(80):
        stamp=(start+timedelta(days=day)).isoformat();d=stamp[:10]
        frames.append({'at':stamp,'items':[item(day=d,observed_at=stamp)]})
    result=historical_experiment(frames);assert result['state']=='COMPLETED' and result['production_changed'] is False
    frames[0]['items'][0]['observed_at']='2027-01-01T00:00:00+00:00'
    with pytest.raises(ValueError,match='Fremtidslekkasje'):historical_experiment(frames)


def test_archive_immutable_daily_and_checksum(local):
    from superfund_learning import archive_frame
    import gzip,base64,hashlib
    archive_frame([item()],'2026-10-05T15:00:00+00:00',engine.DEFAULTS)
    archive_frame([item(price=999)],'2026-10-05T16:00:00+00:00',engine.DEFAULTS)
    index=runtime.read('learning_index.json');assert len(index['frames'])==1
    entry=index['frames'][0];doc=local.read_json(entry['key']);packed=base64.b64decode(doc['gzip_base64'])
    assert hashlib.sha256(packed).hexdigest()==entry['sha256']
    assert json.loads(gzip.decompress(packed))['items'][0]['price']==100


def test_disable_cancels_waiting_buys():
    s,_=step(None,[item()]);s,r=step(s,[item(day='2026-10-06')],'2026-10-06',{'enabled':False})
    assert not s['positions'] and not s['orders']


def test_mobile_page_queues_without_fetch_and_approval_disappears(local,monkeypatch):
    from streamlit.testing.v1 import AppTest
    monkeypatch.setattr(runtime,'catalog_page',lambda *a:pytest.fail('UI fetched a catalogue'))
    proposal={'id':'p1','state':'WAITING_APPROVAL','parameter':'min_week_pct','current':1.0,'proposed':0.5,'source':'test'}
    runtime.write('snapshot.json',{'at':'2026-10-05','model':engine.initial(),'learning':{'proposal':proposal},'parameters':engine.DEFAULTS})
    app=AppTest.from_string('import streamlit as st\nfrom pages.superfund import render_superfund\nrender_superfund(st)').run()
    assert not app.exception
    app.button(key='superfund_queue').click().run()
    assert runtime.read('request.json')['state']=='QUEUED'
    app.checkbox(key='sf_confirm_p1').check().run()
    app.button(key='sf_accept').click().run()
    assert not app.exception
    assert runtime.config()['min_week_pct']==0.5
    assert not [b for b in app.button if b.key=='sf_accept']


def test_same_quote_new_verified_details_reopens_candidate():
    s,_=step(None,[item(detail={})]);assert not s['orders']
    s,_=step(s,[item()]);assert len(s['orders'])==1


def test_manual_parameter_save_preserves_learning_decision(local):
    from superfund_learning import decide_proposal
    proposal={'id':'p1','state':'WAITING_APPROVAL','parameter':'min_week_pct','current':1.0,'proposed':0.5}
    runtime.write('snapshot.json',{'learning':{'proposal':proposal}})
    decide_proposal('p1',True);runtime.save_parameters({'stop_pct':5})
    assert runtime.read('parameter_audit.json')['decisions']['p1']['state']=='IMPLEMENTED'


def test_changed_sector_exposure_rechecked_at_fill():
    rows=[item('NO00000000%02d:78'%n,category=str(n)) for n in (1,2)]
    s,_=step(None,rows,p={'sector_cap_pct':10})
    rows=[{**r,'price_at':'2026-10-06T00:00:00+00:00','observed_at':'2026-10-06T12:00:00+00:00',
           'detail':{**r['detail'],'sectors':[{'exposureType':'TECH','weight':100}]}} for r in rows]
    s,_=step(s,rows,'2026-10-06',{'sector_cap_pct':10})
    assert sum(x['cost_nok'] for x in s['positions'].values())<=100000.01


def test_detail_cache_rotates_and_keeps_held_products(local,monkeypatch):
    monkeypatch.setattr(runtime,'MAX_DETAIL_ITEMS',2)
    old='NO0000000003:78';held='NO0000000004:78'
    index={'pages':{},'details':{old:'2026-01-01',held:'2026-01-02'},'detail_bytes':{old:1,held:1}}
    runtime.write('details/'+old+'.json',{'old':True});runtime.write('details/'+held+'.json',{'held':True})
    runtime.write('snapshot.json',{'model':{'positions':{held:{}}}})
    monkeypatch.setattr(runtime,'details',lambda i:{'verified_at':runtime.now_iso()})
    runtime._enrich([item(detail={})],index,1)
    assert old not in index['details'] and held in index['details']
    assert not runtime.read('details/'+old+'.json',{})


def test_notification_delivery_keeps_unsent_events(local,monkeypatch):
    monkeypatch.setattr(runtime,'deliver_pending',REAL_DELIVERY)
    import notifier
    events=[{'side':'BUY','id':str(i)} for i in range(7)]
    runtime.write('snapshot.json',{'notification_pending':events})
    monkeypatch.setattr(notifier,'send_pushover_alert',lambda *a,**k:True)
    runtime.deliver_pending()
    assert runtime.snapshot()['notification_pending']==events[5:]
    monkeypatch.setattr(notifier,'send_pushover_alert',lambda *a,**k:False)
    runtime.deliver_pending()
    assert runtime.snapshot()['notification_pending']==events[5:]


def test_report_failure_retains_previous_published_report(local,monkeypatch):
    import superfund_reports
    actual=REAL_DELIVERY
    runtime.write('snapshot.json',{'report_pending':True,'report':{'url':'previous'},'notification_pending':[]})
    def fail(s):raise RuntimeError('publication failed')
    monkeypatch.setattr(superfund_reports,'prepare_report_link',fail)
    with pytest.raises(RuntimeError):actual()
    assert runtime.snapshot()['report']=={'url':'previous'} and runtime.snapshot()['report_pending']


def test_observed_returns_do_not_invent_missing_days(local):
    index={'pages':{}};r=raw_row('NO0000000001')
    block={'kind':'fond','page':1,'total':1,'rows':[r],'url':'fixture'}
    runtime._update_page(block,index,'2026-10-05T12:00:00+00:00',{'days':{}})
    r['price_info']['last']['price']=105
    r['price_info']['tick_timestamp']=int(datetime(2026,10,9,tzinfo=timezone.utc).timestamp()*1000)
    runtime._update_page(block,index,'2026-10-09T12:00:00+00:00',{'days':{}})
    row=runtime.all_items(index)[0]
    assert len(row['observations'])==2
    assert row['observed_returns_nok']['1']['return_pct']==pytest.approx(5)
    assert '3' not in row['observed_returns_nok']


def test_archive_total_budget_and_future_details(local,monkeypatch):
    from superfund_learning import archive_frame,historical_experiment
    runtime.write('learning_index.json',{'frames':[],'bytes':64*1024*1024})
    assert archive_frame([item()],'2026-10-05T15:00:00+00:00',engine.DEFAULTS)['state']=='ARCHIVE_BUDGET_REACHED'
    f={'at':'2026-10-05T15:00:00+00:00','items':[item(detail={'verified_at':'2027-01-01T00:00:00+00:00'})]}
    with pytest.raises(ValueError,match='Fremtidslekkasje'):historical_experiment([f],min_days=1)


def test_heavy_entrypoints_defer_while_other_thread_owns_lane(local,monkeypatch):
    from resource_coordinator import execution_lane
    import threading
    import scheduled_runner
    entered=threading.Event();release=threading.Event()
    def owner():
        with execution_lane('manual') as acquired:
            assert acquired;entered.set();release.wait(5)
    thread=threading.Thread(target=owner);thread.start();assert entered.wait(3)
    monkeypatch.setattr(scheduled_runner,'_run_once_locked',lambda:pytest.fail('Cron ran concurrently'))
    try:
        assert scheduled_runner.run_once()['state']=='DEFERRED_BUSY'
        assert runtime.run_batch()['state']=='DEFERRED_BUSY'
    finally:release.set();thread.join(3)


def test_waiting_sp_job_is_resumable_without_replacing_request(monkeypatch):
    import super_portfolio_jobs as jobs
    import super_portfolio_worker as worker
    waiting={'state':'QUEUED','phase':'WAITING_RESOURCE','job_id':'same','execution_token':'token'}
    monkeypatch.setattr(jobs,'get_job',lambda *a:waiting)
    assert jobs.recover_stale_job()==waiting
    monkeypatch.setattr(worker,'run_claimed_job',lambda job_id,execution_token:{'state':'COMPLETED','job_id':job_id})
    assert jobs.run_or_resume_scheduled_job()['job_id']=='same'


def test_fund_report_link_requires_app_login_and_never_publishes_public_pdf(local,monkeypatch):
    import public_report_store as public
    import superfund_reports as reports
    monkeypatch.setattr(public,'publish_durable_pdf',lambda *a,**k:pytest.fail('Anonymous fund PDF publication'))
    monkeypatch.setenv('RENDER_EXTERNAL_URL','https://aksje-app.onrender.com')
    s={'at':'2026-10-05','model':{'last_frame':'1'}}
    link=reports.prepare_report_link(s)
    assert link['access']=='APP_LOGIN_REQUIRED' and link['delivery']=='APP_DOWNLOADS'
    assert link['url']=='https://aksje-app.onrender.com/?aa_nav=superfund'
    assert not local.read_json('public_reports/index.json',[])


def test_archive_clock_is_after_fetched_detail_verification(local,monkeypatch):
    import superfund_learning
    def enrich(rows,index,budget):
        for row in rows:row['detail']={'verified_at':runtime.now_iso()}
        return rows
    def archive(rows,now,p):
        assert all(engine.at(r['detail']['verified_at'])<=engine.at(now) for r in rows)
        return {'state':'ARCHIVED'}
    monkeypatch.setattr(runtime,'_enrich',enrich)
    monkeypatch.setattr(runtime,'refresh_news',lambda rows:None)
    monkeypatch.setattr(superfund_learning,'archive_frame',archive)
    provider=lambda kind,page:{'kind':kind,'page':page,'total':1,'rows':[raw_row('NO0000000001')],'url':'fixture'}
    runtime.run_batch(2,page_provider=provider,fx_provider=lambda:{'days':{}})
    assert runtime.snapshot()['archive_status']['state']=='ARCHIVED'
