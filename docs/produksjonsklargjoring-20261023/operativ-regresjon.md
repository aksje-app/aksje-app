# Supplerende operative prober

Disse tre prøvene ble kjørt utenfor repository-testpakken mot disponibel lokal
PostgreSQL med produksjonsmodus og godkjente, syntetiske kontoer. De verifiserer
faktiske ordinære AUTO-/orchestrator-/arbeiderinnganger. Ingen Render-data brukes.

Lagre blokken i en privat midlertidig Python-fil, sett PYTHONPATH til repository
og tests-katalogen, sett TEST_POSTGRES_URL til lokal testdatabase og kjør filen
med pytest. Dette gjør ingen produksjonsaktivering. Frysingen av klokken gjelder
bare prøvens markedstid, ikke APP_ENVIRONMENT eller aktiveringssperrene.

```python
"""Additional manual production-mode worker smoke probes; disposable localhost PG."""
from datetime import datetime,timedelta,timezone
from test_production_restart import ready,activate,doc,evidence
from test_revision_trade_postgres import pg
from test_simulation_restart import sources,certificate
from test_restart_trading import paper_signal
from services import production_routing as routing


def test_real_paper_auto_entry_and_risk_exit(ready,monkeypatch):
    r=ready;activate(r);instant=datetime.now(timezone.utc)
    instant=(instant+timedelta(days=(7-instant.weekday())%7 or 7)).replace(hour=15,minute=0,second=0,microsecond=0)
    class Frozen(datetime):
        @classmethod
        def now(cls,tz=None):return instant.astimezone(tz or timezone.utc)
    monkeypatch.setattr(routing,'datetime',Frozen)
    prices=[100]
    def provider(ticker,*,currency=None,quote=None,fx_quote=None,at,cost_policy):
        row=evidence(at,prices[0])['TEST'];row['cost_source_ref']=cost_policy['source_ref'];return row
    monkeypatch.setattr(routing,'market_evidence',provider)
    import trading_engine as engine
    context=paper_signal(instant.isoformat())['trade_context'];context['run_id']='ISOLATED ordinary AUTO entry'
    ok,message=engine.auto_trade('TEST',100,'BUY',90,trade_context=context)
    assert ok,message
    assert doc(r,'paper')['account']['positions']['TEST']['quantity']==9.99
    prices[0]=120;context={**context,'run_id':'ISOLATED ordinary AUTO risk exit'}
    ok,message=engine.auto_trade('TEST',120,'HOLD',90,trade_context=context)
    assert ok,message
    account=doc(r,'paper')['account']
    assert account['positions']=={} and len(account['trades'])==2 and account['realized_pnl']>0


def test_real_orchestrator_handoff_to_selected_autonomy(ready,monkeypatch):
    r=ready;activate(r,'autonomy')
    import autonomous_orchestrator as worker
    monkeypatch.setattr(worker,'_write',lambda *a,**k:None)
    monkeypatch.setattr(worker,'_audit',lambda *a,**k:None)
    result=worker.run_post_scan_chain({'run_id':'ISOLATED scheduler handoff','candidates':[]},run_learning=False)
    stage=next(s for s in result['stages'] if s['name']=='AUTONOMOUS_PORTFOLIO')
    assert stage['status']=='OK',stage
    assert any(e['kind']=='STRATEGY_RUN' for e in doc(r,'autonomy')['events'])


def test_real_superportfolio_worker_uses_selected_journal(ready):
    r=ready;activate(r,'super_portfolio')
    import super_portfolio_worker as worker
    at=datetime.now(timezone.utc).isoformat()
    result=worker._evaluate_pipeline({'run_id':'ISOLATED worker job','created_at':at,'candidates':[],
        'market_activation_levels':{'USA':'PRODUCTION'},'regime_fit_score':70},'SCHEDULED')
    assert result['family']=='super_portfolio'
    assert any(e['kind']=='STRATEGY_RUN' for e in doc(r,'super_portfolio')['events'])

```
