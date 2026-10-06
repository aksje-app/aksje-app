from dataclasses import asdict, replace
from datetime import timedelta
from concurrent.futures import ThreadPoolExecutor
import json
from pathlib import Path
import pytest
import autonomous_portfolio as ap
import autonomy_parameter_governance as gov
from services.storage_service import StorageService

@pytest.fixture
def store(tmp_path, monkeypatch):
    storage = StorageService(tmp_path, mode='local', database_url='')
    monkeypatch.setattr(gov, '_storage', lambda: storage)
    monkeypatch.setattr(ap, 'load_parameters', lambda: ap.AutonomousParameters(**{k:v for k,v in storage.read_json(gov.KEY, {}).items() if k in ap.AutonomousParameters.__dataclass_fields__}))
    storage.write_json(gov.KEY, asdict(ap.AutonomousParameters()))
    return storage

def evidence(n=10, m=0):
    return {'trade_ids': [str(i) for i in range(n)], 'observation_ids': [str(i) for i in range(m)],
            'profit_factor': .86, 'expectancy': -10, 'dataset': 'Autonomi uten Paper'}

def proposal(n=10, m=0, after=1.5):
    return gov.queue_proposal('maximum_position_pct', 3., after, 'negativ expectancy', evidence(n,m))

def test_approval_confirmation_atomic_history_and_restart(store):
    p = proposal()
    assert gov.snapshot()['maximum_position_pct'] == 3
    with pytest.raises(PermissionError):
        gov.decide(p['proposal_id'], 'APPROVE', actor='per')
    gov.decide(p['proposal_id'], 'APPROVE', actor='per', confirmed=True)
    restarted = StorageService(store.base_dir, mode='local', database_url='').read_json(gov.KEY)
    assert restarted['maximum_position_pct'] == 1.5
    assert restarted[gov.META]['proposals'][0]['status'] == 'APPLIED'
    h = restarted[gov.META]['history'][0]
    assert h['before'] == {'maximum_position_pct':3.}
    assert h['after'] == {'maximum_position_pct':1.5}
    assert h['actor'] == 'per' and h['timestamp']
    assert restarted[gov.META]['approved_parameters']['maximum_position_pct'] == 1.5
    with pytest.raises(ValueError):
        gov.decide(p['proposal_id'], 'APPROVE', actor='per', confirmed=True)
    assert gov.snapshot()['maximum_position_pct'] == 1.5

def test_rejection_same_data_variants_and_new_evidence(store, monkeypatch):
    time = gov.now()
    monkeypatch.setattr(gov,'now',lambda: time)
    p = proposal(); gov.decide(p['proposal_id'],'REJECT',actor='per')
    assert proposal(40) is None  # cooldown, even when evidence is new
    time += timedelta(days=8)
    assert proposal(after=2.) is None  # variant cannot bypass evidence
    assert proposal(34) is None
    newer = proposal(35, after=2.)
    assert newer['status'] == 'PENDING' and '25 nye handler' in newer['renewed_reason']
    assert gov.snapshot()['maximum_position_pct'] == 3

def test_reproposal_with_new_mature_observations(store, monkeypatch):
    time=gov.now(); monkeypatch.setattr(gov,'now',lambda:time)
    p=proposal(); gov.decide(p['proposal_id'],'REJECT',actor='per')
    time += timedelta(days=8)
    assert proposal(m=20)['status'] == 'PENDING'

def test_defer_persists_and_deduplicates(store):
    p=proposal(); gov.decide(p['proposal_id'],'DEFER',actor='per')
    assert proposal()['proposal_id'] == p['proposal_id']
    assert proposal()['status'] == 'DEFERRED'
    assert len(gov.snapshot()[gov.META]['proposals']) == 1
    assert gov.snapshot()['maximum_position_pct'] == 3

def test_block_and_explicit_unblock(store):
    p=proposal(); gov.decide(p['proposal_id'],'BLOCK',actor='per')
    assert proposal(100) is None
    gov.unblock('maximum_position_pct',actor='per')
    assert proposal(100)['status']=='PENDING'

def test_stale_proposal_manual_edit_and_rollback(store):
    p=proposal()
    gov.save_manual(replace(ap.load_parameters(),maximum_position_pct=2.),actor='per')
    assert gov.snapshot()[gov.META]['proposals'][0]['status']=='STALE'
    with pytest.raises(ValueError):
        gov.decide(p['proposal_id'],'APPROVE',actor='per',confirmed=True)
    gov.rollback(actor='per',confirmed=True)
    assert gov.snapshot()['maximum_position_pct']==3.
    assert gov.snapshot()[gov.META]['history'][0]['status']=='ROLLED_BACK'

def test_rollback_preserves_unrelated_fields_and_does_not_touch_portfolios(store):
    store.write_json('super_portfolio/state.json',{'max_position_pct':15,'positions':['A']})
    store.write_json('autonomous_portfolio/portfolio.json',{'cash':100,'history':[1]})
    p=proposal(); gov.decide(p['proposal_id'],'APPROVE',actor='per',confirmed=True)
    gov.rollback(actor='per',confirmed=True)
    assert gov.snapshot()['maximum_position_pct']==3
    assert gov.snapshot()[gov.META]['proposals'][0]['status']=='ROLLED_BACK'
    assert store.read_json('super_portfolio/state.json')['max_position_pct']==15
    assert store.read_json('autonomous_portfolio/portfolio.json')=={'cash':100,'history':[1]}

def test_concurrent_decisions_apply_once(store):
    p=proposal()
    def apply(_):
        try:
            return gov.decide(p['proposal_id'],'APPROVE',actor='per',confirmed=True)['status']
        except ValueError:
            return 'ALREADY_RESOLVED'
    with ThreadPoolExecutor(2) as pool:
        assert sorted(pool.map(apply,range(2)))==['ALREADY_RESOLVED','APPLIED']
    assert len(gov.snapshot()[gov.META]['history'])==1

def test_failed_mutation_is_atomic(store):
    before=store.read_json(gov.KEY)
    def fail(doc):
        doc['maximum_position_pct']=1.5
        raise RuntimeError('failure')
    with pytest.raises(RuntimeError):
        store.mutate_json(gov.KEY,fail)
    assert store.read_json(gov.KEY)==before

def test_stale_manual_save_cannot_overwrite_new_value(store):
    expected=asdict(ap.load_parameters())
    gov.save_manual(replace(ap.load_parameters(),maximum_position_pct=2),actor='per')
    with pytest.raises(ValueError):
        gov.save_manual(ap.AutonomousParameters(),expected=expected)
    assert gov.snapshot()['maximum_position_pct']==2

def test_layout_and_dataset_labels():
    root=Path(__file__).resolve().parents[1]
    source=(root/'autonomous_portfolio.py').read_text()
    render=source[source.index('def render_autonomous_portfolio'):]
    assert render.index('render_decisions(st)') < render.index('Produksjonsparametre – Autonomi') < render.index('_render_activation_analysis_v1980(st, pd)')
    assert 'flex-direction:column!important' in source
    assert 'Nullstiller ikke historikk' in source
    report=(root/'controlled_parameter_learning.py').read_text()
    assert all(label in report for label in ('PAPER', 'PRODUKSJON', 'LÆRING', 'statistics_basis', 'pending_parameter_proposals'))

def test_parameter_integrity_accepts_approval_and_blocks_unapproved_drift(store, monkeypatch):
    import parameter_integrity as integrity
    import services.storage_service as storage_module
    p=proposal(); gov.decide(p['proposal_id'],'APPROVE',actor='per',confirmed=True)
    monkeypatch.setattr(storage_module,'get_storage_service',lambda:store)
    monkeypatch.setattr(integrity,'_snapshot',lambda:{'parameters':asdict(ap.load_parameters()),'fingerprint':'current'})
    assert integrity.verify_parameter_integrity()['status']=='APPROVED'
    doc=store.read_json(gov.KEY); doc['maximum_position_pct']=2.; store.write_json(gov.KEY,doc)
    pauses=[]; monkeypatch.setattr(ap,'set_status',lambda *args:pauses.append(args))
    assert integrity.verify_parameter_integrity()['status']=='BLOCKED_UNAPPROVED'
    assert pauses

def test_cycle_reloads_approved_sizing_before_other_work(store, monkeypatch):
    p=proposal(); gov.decide(p['proposal_id'],'APPROVE',actor='per',confirmed=True)
    class EndCheck(Exception): pass
    def portfolio():
        assert ap.load_parameters().maximum_position_pct==1.5
        raise EndCheck
    monkeypatch.setattr(ap,'load_portfolio',portfolio)
    with pytest.raises(EndCheck):
        ap.run_autonomous_cycle([], 'AFTER_APPROVAL')

def test_db_failure_aborts_without_local_fallback(tmp_path, monkeypatch):
    storage=StorageService(tmp_path,database_url='postgresql://test',mode='postgres')
    monkeypatch.setattr(storage,'using_postgres',lambda:True)
    monkeypatch.setattr(storage,'init_db',lambda:None)
    def fail(): raise RuntimeError('database down')
    monkeypatch.setattr(storage,'_conn',fail)
    with pytest.raises(RuntimeError):
        storage.mutate_json(gov.KEY,lambda d:{'maximum_position_pct':1.5},{})
    assert not (tmp_path/gov.KEY).exists()

def test_streamlit_buttons_apply_update_slider_and_rollback(tmp_path):
    # Some historic UI tests replace sys.modules['streamlit'] globally. Keep
    # the real Streamlit interaction isolated from those test doubles.
    import os
    import subprocess
    import sys
    code = r"""
from streamlit.testing.v1 import AppTest
import autonomous_portfolio as ap
import autonomy_parameter_governance as gov
import controlled_parameter_learning as cpl
original=gov.render_history
def history(st):
    original(st)
    st.stop()
gov.render_history=history
cpl._read=lambda *a:[]
ap.load_portfolio=lambda:ap.default_portfolio(ap.load_parameters())
p=gov.queue_proposal('maximum_position_pct',3.,1.5,'negativ expectancy',{'profit_factor':.86,'trade_ids':['1'],'observation_ids':[],'dataset':'Autonomi uten Paper'})
at=AppTest.from_string("import streamlit as st\nimport autonomous_portfolio as ap\nst.session_state['auth_user']={'username':'per'}\nap.render_autonomous_portfolio()").run()
assert not at.exception
prefix='autonomy_params'+p['proposal_id']
assert at.button(key=prefix+'APPROVE').disabled
at.checkbox(key=prefix+'confirm').check().run()
at.button(key=prefix+'APPROVE').click().run()
assert not at.exception
assert at.slider(key='alp_pos_v18688').value==1.5
h=gov.snapshot()[gov.META]['history'][-1]
assert h['actor']=='per'
at.checkbox(key='rollback_confirm_'+h['change_id']).check().run()
at.button(key='rollback_'+h['change_id']).click().run()
assert not at.exception
assert at.slider(key='alp_pos_v18688').value==3.
"""
    result=subprocess.run([sys.executable,'-c',code],capture_output=True,text=True,timeout=30,
                          env={**os.environ,'APP_RUNTIME_ROOT':str(tmp_path/'ui'),'DATABASE_URL':'','STORAGE_MODE':'local'})
    assert result.returncode==0, result.stdout+result.stderr

def test_champion_rejection_cannot_immediately_reappear(store, monkeypatch):
    import controlled_parameter_learning as cpl
    from copy import deepcopy
    time=gov.now(); monkeypatch.setattr(gov,'now',lambda:time)
    records={cpl.APPROVALS_PATH:[],cpl.VERSIONS_PATH:[],cpl.HYPOTHESES_PATH:[]}
    monkeypatch.setattr(cpl,'_read',lambda path,default:deepcopy(records.get(path,default)))
    monkeypatch.setattr(cpl,'_write',lambda path,value:records.update({path:deepcopy(value)}))
    monkeypatch.setattr(cpl,'_audit',lambda *a:None)
    monkeypatch.setattr(cpl,'_notify',lambda *a:None)
    monkeypatch.setattr(cpl,'_now',lambda:time.isoformat())
    monkeypatch.setattr(cpl,'_closed_trades',lambda:[{'trade_id':str(i),'pnl':-1} for i in range(count)])
    monkeypatch.setattr(cpl,'_closed_learning_trades',lambda:[])
    monkeypatch.setattr(cpl,'load_learning_observations',lambda:[])
    monkeypatch.setattr(cpl,'calculate_performance',lambda:{'drawdown_pct':0})
    count=10
    trial={'version_id':'TRIAL-1','previous_parameters':{'maximum_position_pct':3},'parameters':{'maximum_position_pct':1.5}}
    first=cpl._queue_promotion_approval(trial,{})
    cpl.resolve_promotion_approval(first['approval_id'],False,note='ikke nå')
    assert cpl._queue_promotion_approval(trial,{})['status']=='REJECTED'
    time += timedelta(days=8)
    assert cpl._queue_promotion_approval(trial,{})['status']=='REJECTED'
    count=35
    renewed=cpl._queue_promotion_approval(trial,{})
    assert renewed['status']=='PENDING' and renewed['approval_id']!=first['approval_id']
