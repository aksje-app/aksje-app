"""The financial history must not overlap optional preparation or quote fetches."""
import gc
import weakref
from copy import deepcopy

import pytest
from services import production_routing as routing, autonomy_nok_companion as companion


class Bundle(dict):
    pass


class StopAtBoundary(Exception):
    pass


@pytest.mark.parametrize('boundary', ['preparation', 'quotes'])
def test_autonomy_releases_verified_history_before_external_work(monkeypatch, boundary):
    refs = []
    approval = dict(period_id='period', settings={}, cost_policy={})
    document = dict(account={'positions': {}}, events=[], status='ACTIVE',
                    opening_sha256='opening', approval={'scope': 'production'})
    def select(*a, **kw):
        bundle = Bundle(accounts={'autonomy': deepcopy(document)},
                        production_controls={'autonomy': {'status': 'RUNNING'}})
        refs.append(weakref.ref(bundle))
        return dict(pointer={'period_id': 'period', 'family': 'autonomy'},
                    approval=deepcopy(approval), bundle=bundle)
    monkeypatch.setattr(routing.control, 'selected', select)
    monkeypatch.setattr(routing.control, 'get_storage_service', lambda: object())
    monkeypatch.setattr(routing, '_account_projection', lambda *a, **kw: {'positions': {}, 'cash': 500000})
    def check():
        gc.collect()
        assert refs[0]() is None, 'full verified bundle retained during ' + boundary
        raise StopAtBoundary
    def prepare(*a, **kw):
        if boundary == 'preparation': check()
        return {'candidates': [], 'settings': {}}
    def quotes(*a, **kw): check()
    monkeypatch.setattr(companion, 'prepare', prepare)
    monkeypatch.setattr(routing, '_collect_execution_evidence', quotes)
    with pytest.raises(StopAtBoundary):
        routing.autonomy([], 'run')


def test_detached_evidence_keeps_latest_held_quote_without_history():
    quote={'price': 10, 'source': 'documented', 'observed_at': '2026-11-16T08:00:00+00:00'}
    doc=dict(account={'positions': {'A.OL': {'currency':'NOK','quantity':2}}},
             events=[{'kind':'STRATEGY_RUN','payload':{'state':{'positions':{'A.OL':{'execution_quote':{'price':1}}}}}},
                     {'kind':'STRATEGY_RUN','payload':{'state':{'positions':{'A.OL':{'execution_quote':quote,'history':['old']}}}}}],
             status='ACTIVE', opening_sha256='opening',approval={'scope':'production'})
    chosen=dict(pointer={'family':'autonomy'},approval={'period_id':'period','cost_policy':{'source_ref':'cost'}},
                bundle={'accounts':{'autonomy':doc}})
    source=routing._execution_source('autonomy',chosen)
    assert source['document']['account']['positions']==doc['account']['positions']
    assert source['document']['events']==[{'kind':'STRATEGY_RUN','payload':{'state':{'positions':{'A.OL':{'execution_quote':quote}}}}}]
    assert source['account_ref']['approval_sha256']==routing.digest(doc['approval'])
    source['document']['account']['positions']['A.OL']['quantity']=99
    source['document']['events'][0]['payload']['state']['positions']['A.OL']['execution_quote']['price']=99
    source['cost_policy']['source_ref']='changed'
    assert doc['account']['positions']['A.OL']['quantity']==2
    assert quote['price']==10
    assert chosen['approval']['cost_policy']['source_ref']=='cost'


@pytest.mark.parametrize('missing_quote', [False, True])
def test_detached_source_preserves_real_held_quote_gate(monkeypatch, missing_quote):
    from test_execution_evidence_handoff import chosen, raw_quote, NOW, no_network
    no_network(monkeypatch)
    selected=chosen({'A.OL': {'currency':'NOK', 'quantity':2}})
    selected['bundle']['accounts']['autonomy']['events']=[
        {'kind':'STRATEGY_RUN','payload':{'state':{'positions':{
            'A.OL': {'execution_quote': {} if missing_quote else raw_quote()}}}}}]
    source=routing._execution_source('autonomy',selected)
    when=NOW.isoformat()
    if missing_quote:
        with pytest.raises(routing.ExecutionEvidenceError) as original:
            routing._collect_execution_evidence('autonomy',{},selected['bundle']['accounts']['autonomy'],
                                                selected['approval']['cost_policy'],at=when)
        with pytest.raises(routing.ExecutionEvidenceError) as detached:
            routing._context_from_source('autonomy','run',[],source,at=when)
        assert detached.value.code==original.value.code=='MISSING_EXECUTION_QUOTE'
    else:
        evidence,blocked,at=routing._collect_execution_evidence('autonomy',{},selected['bundle']['accounts']['autonomy'],
                                                              selected['approval']['cost_policy'],at=when)
        detached=routing._context_from_source('autonomy','run',[],source,at=when)
        assert detached['evidence']==evidence
        assert detached['evidence']['A.OL']['price']==100
        assert detached['evidence_blocks']==blocked==[]
        assert detached['at']==at
