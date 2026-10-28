"""Complete signed activation on isolated PostgreSQL; NEVER production fixtures.

Uses genuine CMS archive, physical restore, native source fingerprints, original
DRAFT bundle, real request/sign/activate and direct SQL-backed route reads.
"""
from copy import deepcopy
from datetime import datetime, timedelta, timezone
import hashlib
import json
import os
from pathlib import Path
import shutil
import tarfile
import pytest
from test_production_restart import ready, doc, direct, bound_cost_evidence
from test_revision_trade_postgres import pg
from test_simulation_restart import sources, certificate
from test_restart_trading import evidence
from services import production_restart as control, simulation_restart as restart, simulation_archive as archive
from services import activation_preflight as preflight, production_routing as routing
from services.economic_opening import digest
from services.storage_service import StorageService
from tools.nok_operator.operator_common import policies


def preflight_grants(r,monkeypatch,*,runtime_evidence=None):
    # No provider, market scanner or fake live_preview can make this pass.
    monkeypatch.setattr(routing,'market_evidence',lambda *a,**kw:pytest.fail('Activation must not fetch execution quotes'))
    monkeypatch.setattr(routing,'live_preview',lambda *a,**kw:pytest.fail('Preflight is NOT a market run'))
    settings={f:routing.strategy_settings(f,storage=r['pg'],require_stored=True) for f in restart.CAPITALS}
    costs=policies();result={};receipts={}
    inputs={'paper':[{'ticker':'CLOSED','signal':'HOLD','operation':'AUTO'}],
            'autonomy':[{'ticker':'DELAYED.OL','portfolio_action':'BUY'}],
            'super_portfolio':dict(run_id='SPM-20261024-001559',candidates=[
                dict(ticker='ORNBV.HE',source='Super Portfolio independent market universe')])}
    for family in restart.CAPITALS:
        receipts[family]=preflight.inspect(r['bundle']['period_id'],family,settings=settings[family],
            cost_policy=costs[family],restore_review=r['review'],strategy_input=inputs[family],
            runtime_evidence=runtime_evidence,storage=r['pg'])
        payload=control.request(r['bundle']['period_id'],family,actor='ISOLATED PERSONAL B TEST',
            approval_ref='EXACT SYNTHETIC B REVIEW',at=datetime.now(timezone.utc).isoformat(),
            restore_review=r['review'],settings=settings[family],cost_policy=costs[family],storage=r['pg'],
            activation_preflight=receipts[family])
        assert payload['schema']=='NOK_PRODUCTION_GRANT_V2'
        result[family]=control.sign(payload,r['key'])
    return result,receipts


def activate_one(r,grant,**changes):
    options=dict(confirmation=digest(grant['payload']),archive_root=r['root'],certificate=r['cert'],
        private_key=r['key'],restore_destination=r['destination'],storage=r['pg'])
    options.update(changes)
    return control.activate(grant,**options)


@pytest.mark.parametrize('market_state',['ALL_MARKETS_CLOSED','PARTIAL_DELAYED_QUOTES'])
def test_entire_three_account_chain_without_execution_quotes(ready,monkeypatch,market_state):
    import market_hours
    monkeypatch.setattr(market_hours,'is_market_open_for_ticker',lambda ticker:market_state!='ALL_MARKETS_CLOSED' and ticker=='CLOSED')
    r=ready;before=deepcopy(r['pg'].read_json(restart._key(r['bundle']['period_id'])))
    legacy={k:r['pg'].read_json(k) for k in ('learning/observations.json','paper_trading/portfolio.json',
            'autonomous_portfolio/portfolio.json','super_portfolio/state.json')}
    monkeypatch.setenv('STORAGE_MODE','postgres');monkeypatch.setenv('ALLOW_LOCAL_STORAGE_FALLBACK','false')
    reviewed=archive.verify_archive(r['root'],r['bundle']['archive']['archive_id'],certificate=r['cert'],private_key=r['key'])
    preserved=archive.runtime_source_evidence(reviewed,r['destination']/'payload')
    grants,receipts=preflight_grants(r,monkeypatch,runtime_evidence=preserved)
    assert r['pg'].read_json(restart._key(r['bundle']['period_id']))==before
    for receipt in receipts.values():
        assert receipt['mode']==preflight.MODE and receipt['orders_created']==0
        assert not receipt['actual_market_run_performed'] and not receipt['quotes_obtained']
    from market_universe import MARKET_ACTIVATION_LEVELS
    assert receipts['super_portfolio']['market_activation_levels']==MARKET_ACTIVATION_LEVELS
    assert receipts['super_portfolio']['market_activation_levels']['Finland']=='SHADOW'
    for family,grant in grants.items():
        activate_one(r,grant)
        selected=control.selected(family,storage=r['pg'])
        assert selected['pointer']['grant_sha256']==digest(grant)
        current=doc(r,family)
        assert current['status']=='ACTIVE'
        assert current['account']['cash']==restart.CAPITALS[family]
        assert current['account']['positions']=={} and current['account']['trades']==[]
        assert selected['bundle']['production_controls'][family]['status']=='RUNNING'
    for key,original in legacy.items():assert r['pg'].read_json(key)==original
    # Reopen a real connection, not an in-memory/cached result.
    connection=r['pg']._conn()
    try:
        with connection.cursor() as q:
            q.execute("SELECT count(*) FROM app_kv_store WHERE name LIKE 'simulation_restarts/routes/%'")
            assert q.fetchone()[0]==3
    finally:connection.close()
    # Stale price or stale FX still blocks real isolated simulated trading.
    at=datetime.now(timezone.utc).isoformat();stale=(datetime.now(timezone.utc)-timedelta(hours=1)).isoformat()
    for family in restart.CAPITALS:
        old=deepcopy(doc(r,family));signed_policy=grants[family]['payload']['cost_policy']
        for stale_part in ('price','fx'):
            quote=bound_cost_evidence(evidence(at)['TEST'],signed_policy)
            if stale_part=='price':quote['observed_at']=stale
            else:quote['fx_quote']['observed_at']=stale
            with pytest.raises(ValueError):
                from services.restart_trading import Session,Memory
                Session(period_id=r['bundle']['period_id'],family=family,run_id='stale-'+stale_part,
                    at=at,evidence={'TEST':quote},settings=grants[family]['payload']['settings'],
                    memory=Memory(r['pg'].read_json(restart._key(r['bundle']['period_id'])),restart._key(r['bundle']['period_id'])))
            assert doc(r,family)==old


def test_signed_preflight_tampering_and_settings_changes_block_before_activation(ready,monkeypatch):
    r=ready;grants,receipts=preflight_grants(r,monkeypatch)
    altered=deepcopy(grants['paper']);altered['payload']['activation_preflight']['orders_created']=1
    with pytest.raises(ValueError,match='signature'):activate_one(r,altered)
    false=deepcopy(receipts['paper']);false['actual_market_run_performed']=True
    false['receipt_sha256']=digest({k:v for k,v in false.items() if k!='receipt_sha256'})
    with pytest.raises(ValueError,match='Invalid signed'):
        control.request(r['bundle']['period_id'],'paper',actor='isolated',approval_ref='test',
            at=datetime.now(timezone.utc).isoformat(),restore_review=r['review'],settings=grants['paper']['payload']['settings'],
            cost_policy=policies()['paper'],storage=r['pg'],activation_preflight=false)
    rules=r['pg'].read_json('settings/trading_rules.json');rules['start_cash']=777
    r['pg'].write_json('settings/trading_rules.json',rules)
    with pytest.raises(ValueError,match='Stored strategy settings changed'):activate_one(r,grants['paper'])
    assert all(doc(r,f)['status']=='DRAFT' for f in restart.CAPITALS)


def rehydrate(r,archive_root,destination):
    archive.verify_archive(archive_root,r['bundle']['archive']['archive_id'],certificate=r['cert'],private_key=r['key'])
    destination.mkdir(mode=0o700);packed=destination/'payload.tar'
    archive._openssl(['cms','-decrypt','-binary','-inform','DER','-in',archive_root/r['bundle']['archive']['archive_id']/'archive.cms',
        '-recip',r['cert'],'-inkey',r['key'],'-out',packed])
    with tarfile.open(packed) as tar:tar.extractall(destination/'payload',filter='data')
    (destination/'restore-review.json').write_text(json.dumps(r['review']))
    archive.verify_restore_destination(destination,r['review'])


def test_redeploy_and_disconnect_resume_exact_signed_accounts_without_recreating_them(ready,monkeypatch,tmp_path):
    r=ready
    monkeypatch.setenv('STORAGE_MODE','postgres');monkeypatch.setenv('ALLOW_LOCAL_STORAGE_FALLBACK','false')
    # Simulate a truly ABSENT old runtime after redeploy. Never mask a changed live root.
    r['sources'].rename(tmp_path/'retained-original-runtime')
    reviewed=archive.verify_archive(r['root'],r['bundle']['archive']['archive_id'],certificate=r['cert'],private_key=r['key'])
    preserved=archive.runtime_source_evidence(reviewed,r['destination']/'payload')
    assert preserved['runtime']['state']=='ABSENT_SOURCE_ARCHIVED_FILES_VERIFIED'
    grants,_=preflight_grants(r,monkeypatch,runtime_evidence=preserved)
    original_write=r['pg'].write_json_immutable
    def lost_route(key,value):
        if key==control.route_key('paper'):raise ConnectionError('ISOLATED SSH loss after authorization but before route')
        return original_write(key,value)
    monkeypatch.setattr(r['pg'],'write_json_immutable',lost_route)
    with pytest.raises(ConnectionError):activate_one(r,grants['paper'])
    assert doc(r,'paper')['status']=='ACTIVE' and r['pg'].read_json(control.route_key('paper'),None) is None
    monkeypatch.setattr(r['pg'],'write_json_immutable',original_write)
    # Original encrypted PC copy survives. Render verification files do not.
    pc_copy=tmp_path/'pc-independent-archive';shutil.copytree(r['root'],pc_copy)
    r['root'].rename(tmp_path/'old-container-archive');r['destination'].rename(tmp_path/'old-container-restore')
    fresh=tmp_path/'new-container';fresh.mkdir(mode=0o700)
    new_archive=fresh/'archives';shutil.copytree(pc_copy,new_archive);new_archive.chmod(0o700)
    new_restore=fresh/'restored';rehydrate(r,new_archive,new_restore)
    # New storage object = no old Python process state or cache.
    reopened=StorageService(tmp_path/'new-process',database_url=r['pg'].database_url,mode='postgres',allow_local_fallback=False)
    for family,grant in grants.items():
        activate_one(r,grant,archive_root=new_archive,restore_destination=new_restore,storage=reopened)
        selected=control.selected(family,storage=reopened)
        assert selected['bundle']['production_controls'][family]['grant']==grant
        assert selected['bundle']['accounts'][family]['account']['cash']==restart.CAPITALS[family]
    # Repeating the SAME signed requests only confirms existing routes.
    snapshots={f:deepcopy(doc(r,f)) for f in restart.CAPITALS}
    for family,grant in grants.items():activate_one(r,grant,archive_root=new_archive,restore_destination=new_restore,storage=reopened)
    assert snapshots=={f:doc(r,f) for f in restart.CAPITALS}
    assert archive.sha(new_archive/r['bundle']['archive']['archive_id']/'archive.cms')==r['bundle']['archive']['cipher_sha256']


def test_missing_runtime_cannot_hide_changed_files_or_enable_fallback(ready,monkeypatch):
    r=ready;reviewed=archive.verify_archive(r['root'],r['bundle']['archive']['archive_id'],certificate=r['cert'],private_key=r['key'])
    (r['sources']/'learning.json').write_text('{"tampered":true}')
    with pytest.raises(ValueError,match='Runtime changed'):archive.runtime_source_evidence(reviewed,r['destination']/'payload')
    r['sources'].rename(r['sources'].with_name('removed-runtime'))
    monkeypatch.setenv('STORAGE_MODE','postgres');monkeypatch.setenv('ALLOW_LOCAL_STORAGE_FALLBACK','true')
    with pytest.raises(ValueError,match='without fallback'):archive.runtime_source_evidence(reviewed,r['destination']/'payload')


def test_stricter_frozen_policy_is_not_promoted_and_historical_pipeline_is_unchanged():
    from market_universe import MARKET_ACTIVATION_LEVELS
    original={'run_id':'SPM-20261024-001559','candidates':[]}
    assert preflight.frozen_market_policy(original)==MARKET_ACTIVATION_LEVELS
    assert 'market_activation_levels' not in original
    stricter=dict(original,market_activation_levels={'Norge':'SHADOW','Finland':'OFF'})
    result=preflight.frozen_market_policy(stricter)
    assert result['Norge']=='SHADOW' and result['USA']=='OFF' and result['Finland']=='OFF'
    with pytest.raises(ValueError,match='differ from governed'):
        preflight.frozen_market_policy({'market_activation_levels':{'Finland':'PRODUCTION'}})


def test_absent_empty_archived_root_has_no_fabricated_files(tmp_path,monkeypatch):
    monkeypatch.setenv('STORAGE_MODE','postgres');monkeypatch.setenv('ALLOW_LOCAL_STORAGE_FALLBACK','false')
    original=tmp_path/'absent';restored=tmp_path/'restored';restored.mkdir()
    reviewed={'manifest':{'source_roots':{'empty':str(original)},'source_inventory':{'empty':{}}}}
    result=archive.runtime_source_evidence(reviewed,restored)
    assert result['empty']['inventory_sha256']==digest({})
    assert not original.exists() and not (restored/'runtime'/'empty').exists()
