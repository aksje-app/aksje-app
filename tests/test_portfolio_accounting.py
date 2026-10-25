"""End-to-end draft/approval/fill/mark/recovery tests on isolated storage only."""
from copy import deepcopy
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
import json

import pytest
from test_revision_trade_postgres import pg
from services import portfolio_accounting as accounting
from services.economic_opening import opening_account, digest
from services.economic_ledger import reconcile
from services.storage_service import StorageService

NOW = datetime.now(timezone.utc).replace(microsecond=0)
AT = NOW.isoformat()


def quote(rate=10, currency='USD', at=AT):
    return dict(currency=currency,base_currency='NOK',rate=rate,observed_at=at,source='TEST ONLY dated fixing')


def opening(positions=False):
    doc=dict(at=AT,base_currency='NOK',cash_nok=100000,source_ref='TEST ONLY cash statement',positions={})
    if positions:
        doc['positions']['TEST']=dict(quantity=10,cost_basis_nok=12000,currency='USD',price=100,
            price_observed_at=AT,price_source='TEST ONLY raw close',fx_quote=quote(),
            source_ref='TEST ONLY holdings statement',cost_basis_source_ref='TEST ONLY historical cost statement')
    return doc


def fill(identity='BUY', side='BUY', quantity=10, price=100, rate=10, fee=10, at=AT):
    return dict(trade_id=identity,ticker='TEST',side=side,quantity=quantity,price=price,currency='USD',
        observed_at=at,source='TEST ONLY raw executed price',at=at,fee=fee,cost_currency='NOK',
        fx_quote=quote(rate,at=at),cost_components=dict(brokerage_nok=fee*.6,fx_cost_nok=fee*.4,other_nok=0),
        cost_source_ref='TEST ONLY explicit simulation costs')


@pytest.fixture
def local(tmp_path,monkeypatch):
    monkeypatch.setenv('APP_ENVIRONMENT','test')
    return StorageService(tmp_path,database_url='',mode='local')


def activate(storage,family='paper',positions=False):
    prepared=accounting.prepare(family,opening(positions),prepared_by='test operator',storage=storage)
    approval=dict(approved_by='test reviewer',approval_ref='TEST ONLY explicit approval',family=family,
        opening_sha256=prepared['opening_sha256'],start_at=AT,approved_at=AT,scope='test')
    return accounting.approve(family,approval,storage=storage)


@pytest.mark.parametrize('family',accounting.FAMILIES)
def test_complete_accounting_chain_and_recovery(local,family):
    legacy={'cash':123,'positions':{'OLD':{'quantity':4}},'loss':-2000,'trades':[{'id':'historic-loss'}]}
    local.write_json('legacy/'+family+'.json',legacy)
    activated=activate(local,family)
    accounting.settle(family,fill(),storage=local)
    accounting.settle(family,fill('ADD',quantity=5,fee=5),storage=local)
    accounting.settle(family,fill('PARTIAL','SELL',3,110,11,3),storage=local)
    result=accounting.report(family,storage=local,at=NOW)
    period=result['new_period']
    assert result['status']=='ACTIVE'
    assert period['verification']['status']=='BESTÅTT'
    assert period['positions']['TEST']['quantity']==12
    assert period['positions']['TEST']['cost_basis_base']==pytest.approx(12012)
    assert period['realized_pnl_nok']==pytest.approx(624)
    assert period['verification']['verified_nav']==pytest.approx(103132)
    assert period['unrealized_pnl_nok']==pytest.approx(2508)
    assert period['period_net_pnl_nok']==pytest.approx(3132)
    assert sum(period['costs_nok'].values())==18
    restarted=StorageService(local.base_dir,database_url=local.database_url,mode=local.mode,allow_local_fallback=False if local.mode=='postgres' else True)
    before=restarted.read_json(accounting.key(family))
    assert accounting.settle(family,fill('PARTIAL','SELL',3,110,11,3),storage=restarted)==before
    assert accounting.approve(family,activated['approval'],storage=restarted)==before
    accounting.settle(family,fill('FINAL','SELL',12,110,11,12),storage=restarted)
    final=accounting.report(family,storage=restarted,at=NOW)['new_period']
    assert final['verification']['verified_nav']==103120
    assert final['positions']=={}
    assert final['realized_pnl_nok']==3120
    assert final['period_net_pnl_nok']==3120
    assert local.read_json('legacy/'+family+'.json')==legacy
    assert len(final['trades'])==4
    assert len(final['journal'])==6


def test_opening_positions_preserve_historical_loss_and_period_boundary(local):
    activate(local,positions=True)
    first=accounting.report('paper',storage=local,at=NOW)['new_period']
    assert first['carried_opening_unrealized_nok']==-2000
    assert first['unrealized_pnl_nok']==-2000
    assert first['period_net_pnl_nok']==0
    assert first['verification']['verified_net_return_pct']==0
    accounting.settle('paper',fill('ADD',quantity=5,fee=5),storage=local)
    pos=accounting.report('paper',storage=local,at=NOW)['new_period']['positions']['TEST']
    assert 'average_price' not in pos  # Cannot infer historic USD entry from opening FX.
    assert pos['cost_basis_base']==17005
    accounting.settle('paper',fill('EXIT','SELL',15,100,10,15),storage=local)
    period=accounting.report('paper',storage=local,at=NOW)['new_period']
    assert period['realized_pnl_nok']==-2020
    assert period['period_net_pnl_nok']==-20
    assert period['carried_opening_unrealized_nok']==-2000
    assert period['verification']['verified_nav']==109980


def test_fx_marks_reconcile_with_journal_and_reject_partial_or_future(local):
    activate(local)
    accounting.settle('paper',fill(),storage=local)
    mark=dict(price=100,observed_at=AT,source='TEST ONLY close',fx_quote=quote(11))
    accounting.mark('paper',{'TEST':mark},at=AT,storage=local)
    result=accounting.report('paper',storage=local,at=NOW)['new_period']
    assert result['verification']['verified_nav']==100990
    assert result['period_net_pnl_nok']==990
    before=local.read_json(accounting.key('paper'))
    assert accounting.mark('paper',{'TEST':mark},at=AT,storage=local)==before
    with pytest.raises(ValueError):accounting.mark('paper',{},at=AT,storage=local)
    with pytest.raises(ValueError):accounting.mark('paper',{'TEST':{**mark,'observed_at':(NOW+timedelta(days=1)).isoformat()}},at=AT,storage=local)
    assert local.read_json(accounting.key('paper'))==before
    stale=accounting.report('paper',storage=local,at=NOW+timedelta(days=6))['new_period']
    assert stale['verification']['verified_nav'] is None
    assert stale['period_net_pnl_nok'] is None


@pytest.mark.parametrize('missing', ['source_ref','cash_nok','at','base_currency','positions'])
def test_opening_missing_facts_rejected(local,missing):
    doc=opening();doc.pop(missing)
    with pytest.raises((ValueError,KeyError)):accounting.prepare('paper',doc,prepared_by='test',storage=local)
    assert local.read_json(accounting.key('paper')) is None


@pytest.mark.parametrize('missing',['quantity','cost_basis_nok','cost_basis_source_ref','source_ref','price','price_observed_at','price_source','fx_quote','currency'])
def test_opening_position_requires_all_evidence(local,missing):
    doc=opening(True);doc['positions']['TEST'].pop(missing)
    with pytest.raises((ValueError,KeyError)):accounting.prepare('paper',doc,prepared_by='test',storage=local)
    assert local.read_json(accounting.key('paper')) is None


def test_draft_cannot_trade_reset_or_leak_into_legacy(local):
    prepared=accounting.prepare('autonomy',opening(),prepared_by='test',storage=local)
    assert accounting.report('autonomy',storage=local,at=NOW)['status']=='DRAFT'
    assert accounting.prepare('autonomy',opening(),prepared_by='test',storage=local)==prepared
    changed=opening();changed['cash_nok']=200000
    with pytest.raises(ValueError):accounting.prepare('autonomy',changed,prepared_by='test',storage=local)
    with pytest.raises(ValueError):accounting.settle('autonomy',fill(),storage=local)
    assert local.read_json(accounting.key('autonomy'))==prepared
    assert accounting.report('paper',storage=local)['status']=='NOT_PREPARED'
    with pytest.raises(ValueError):accounting.prepare('superfund',opening(),prepared_by='test',storage=local)


@pytest.mark.parametrize('field,value',[('opening_sha256','wrong'),('family','autonomy'),('scope','production'),('start_at','2020-01-01T00:00:00Z'),('approved_by',''),('approval_ref','')])
def test_approval_must_bind_exact_opening(local,field,value):
    doc=activate(local)
    bad={**doc['approval'],field:value}
    with pytest.raises(ValueError):accounting.approve('paper',bad,storage=local)
    assert local.read_json(accounting.key('paper'))==doc


@pytest.mark.parametrize('environment',['production',None])
def test_production_activation_defaults_to_blocked(local,monkeypatch,environment):
    doc=accounting.prepare('paper',opening(),prepared_by='test',storage=local)
    if environment is None:
        monkeypatch.delenv('APP_ENVIRONMENT',raising=False)
    else:
        monkeypatch.setenv('APP_ENVIRONMENT',environment)
    monkeypatch.delenv('ECONOMIC_PRODUCTION_ACTIVATION_ENABLED',raising=False)
    with pytest.raises(ValueError,match='Production activation'):accounting.approve('paper',{},storage=local)
    assert local.read_json(accounting.key('paper'))==doc


@pytest.mark.parametrize('change',[{'quantity':100000},{'fee':11},{'fx_quote':None},{'cost_components':None},
    {'observed_at':'2020-01-01T00:00:00Z'},{'quantity':True},{'price':float('nan')}, {'side':'SELL'}])
def test_invalid_fills_leave_everything_unchanged(local,change):
    before=activate(local)
    with pytest.raises(ValueError):accounting.settle('paper',{**fill(),**change},storage=local)
    assert local.read_json(accounting.key('paper'))==before


@pytest.mark.parametrize('kind',['cash','shares','cost_basis','journal','opening','approval','missing_trade','hash_rebuilt'])
def test_tampering_is_detected_before_reporting_or_trading(local,kind):
    activate(local);accounting.settle('paper',fill(),storage=local)
    doc=local.read_json(accounting.key('paper'))
    if kind=='cash':doc['account']['cash']+=1
    if kind=='shares':doc['account']['positions']['TEST']['quantity']+=1
    if kind=='cost_basis':doc['account']['positions']['TEST']['cost_basis_base']+=1
    if kind=='journal':doc['events'][-1]['payload']['fee']+=1
    if kind=='opening':doc['account']['opening_document']['cash_nok']+=1
    if kind=='approval':doc['approval']['approved_by']='someone else'
    if kind=='missing_trade':doc['events'].pop()
    if kind=='hash_rebuilt':
        doc['events'][-1]['payload']['quantity']=9
        doc['events'][-1]['hash']=digest({k:v for k,v in doc['events'][-1].items() if k!='hash'})
    local.write_json(accounting.key('paper'),doc)
    assert accounting.report('paper',storage=local,at=NOW)['status']=='INTEGRITY_ERROR'
    with pytest.raises(ValueError):accounting.settle('paper',fill('NEXT'),storage=local)
    assert local.read_json(accounting.key('paper'))==doc


def test_concurrent_retry_and_distinct_fills_are_serialized(local):
    activate(local)
    with ThreadPoolExecutor(max_workers=4) as pool:
        list(pool.map(lambda _:accounting.settle('paper',fill(),storage=local),range(4)))
    with ThreadPoolExecutor(max_workers=4) as pool:
        list(pool.map(lambda i:accounting.settle('paper',fill('ADD-'+str(i),quantity=1,fee=1),storage=local),range(4)))
    doc=local.read_json(accounting.key('paper'));accounting.verify(doc)
    assert len(doc['account']['trades'])==5
    assert doc['account']['positions']['TEST']['quantity']==14
    assert doc['account']['cash']==85986


def test_pg_complete_chain(pg,monkeypatch):
    monkeypatch.setenv('APP_ENVIRONMENT','test')
    test_complete_accounting_chain_and_recovery(pg,'super_portfolio')


def test_pg_concurrent_retry(pg,monkeypatch):
    monkeypatch.setenv('APP_ENVIRONMENT','test')
    test_concurrent_retry_and_distinct_fills_are_serialized(pg)


def test_pg_failure_rolls_back_account_and_journal(pg,monkeypatch):
    monkeypatch.setenv('APP_ENVIRONMENT','test')
    before=activate(pg)
    connection=pg._conn()
    try:
        with connection.cursor() as cur:
            cur.execute("""CREATE FUNCTION reject_economic() RETURNS trigger LANGUAGE plpgsql AS $$
            BEGIN IF NEW.name LIKE 'economic_accounts/%' THEN RAISE EXCEPTION 'injected economic commit failure'; END IF; RETURN NEW; END $$""")
            cur.execute('CREATE TRIGGER economic_failure BEFORE UPDATE ON app_kv_store FOR EACH ROW EXECUTE FUNCTION reject_economic()')
        connection.commit()
    finally:connection.close()
    with pytest.raises(Exception,match='injected economic commit failure'):accounting.settle('paper',fill(),storage=pg)
    assert pg.read_json(accounting.key('paper'))==before
    connection=pg._conn()
    try:
        with connection.cursor() as cur:cur.execute('DROP TRIGGER economic_failure ON app_kv_store')
        connection.commit()
    finally:connection.close()
    accounting.settle('paper',fill(),storage=pg)
    assert accounting.report('paper',storage=pg,at=NOW)['new_period']['verification']['status']=='BESTÅTT'


@pytest.mark.parametrize('family,module',[('paper','paper_store'),('autonomy','autonomous_portfolio'),('super_portfolio','services.super_portfolio_store')])
def test_explicit_portfolio_fill_adapters(local,family,module):
    import importlib
    activate(local,family)
    adapter=importlib.import_module(module).record_documented_nok_fill
    adapter(fill(),storage=local)
    result=accounting.report(family,storage=local,at=NOW)['new_period']
    assert result['verification']['status']=='BESTÅTT'
    assert result['cash_nok']==89990
    before=local.read_json(accounting.key(family))
    with pytest.raises(ValueError):adapter({**fill(),'quantity':9},storage=local)
    assert local.read_json(accounting.key(family))==before


def test_lost_commit_acknowledgement_recovers_without_double_booking(local,monkeypatch):
    activate(local)
    real_mutate=local.mutate_json
    def lost_ack(*args,**kwargs):
        real_mutate(*args,**kwargs)
        raise OSError('TEST ONLY lost commit acknowledgement')
    monkeypatch.setattr(local,'mutate_json',lost_ack)
    with pytest.raises(OSError):accounting.settle('paper',fill(),storage=local)
    restarted=StorageService(local.base_dir,database_url='',mode='local')
    accounting.settle('paper',fill(),storage=restarted)
    result=accounting.report('paper',storage=restarted,at=NOW)['new_period']
    assert len(result['trades'])==1
    assert len(result['journal'])==3
    assert result['cash_nok']==89990


def test_retry_after_later_mark_and_out_of_order_events(local):
    activate(local);accounting.settle('paper',fill(),storage=local)
    later=(NOW+timedelta(minutes=1)).isoformat()
    mark=dict(price=100,observed_at=later,source='TEST ONLY mark',fx_quote=quote(11,at=later))
    before=accounting.mark('paper',{'TEST':mark},at=later,storage=local)
    assert accounting.settle('paper',fill(),storage=local)==before
    with pytest.raises(ValueError):accounting.settle('paper',fill('NEW-OLD'),storage=local)
    newer=(NOW+timedelta(minutes=2)).isoformat()
    bought=accounting.settle('paper',fill('LATER',quantity=1,at=newer),storage=local)
    with pytest.raises(ValueError):accounting.mark('paper',{'TEST':mark},at=later,storage=local)
    assert local.read_json(accounting.key('paper'))==bought


def test_test_approval_cannot_execute_in_production(local,monkeypatch):
    before=activate(local)
    monkeypatch.setenv('APP_ENVIRONMENT','production')
    with pytest.raises(ValueError,match='scope'):accounting.settle('paper',fill(),storage=local)
    assert local.read_json(accounting.key('paper'))==before


def test_report_cannot_verify_future_cash_or_opening(local):
    activate(local)
    assert accounting.report('paper',storage=local,at=NOW-timedelta(seconds=1))['new_period']['verification']['verified_nav'] is None
    later=(NOW+timedelta(minutes=2)).isoformat()
    accounting.settle('paper',fill('FUTURE-BUY',at=later),storage=local)
    accounting.settle('paper',fill('FUTURE-SELL','SELL',at=later),storage=local)
    assert accounting.report('paper',storage=local,at=NOW)['new_period']['verification']['verified_nav'] is None


def test_three_families_have_independent_cash_positions_and_journals(local):
    before={family:activate(local,family) for family in accounting.FAMILIES}
    accounting.settle('paper',fill(),storage=local)
    for family in ('autonomy','super_portfolio'):
        assert local.read_json(accounting.key(family))==before[family]
        assert accounting.report(family,storage=local,at=NOW)['new_period']['verification']['verified_nav']==100000
    assert accounting.report('paper',storage=local,at=NOW)['new_period']['verification']['verified_nav']==99990
