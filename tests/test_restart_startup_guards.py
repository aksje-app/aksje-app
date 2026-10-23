"""Deployment/startup cannot select or activate a restart account implicitly."""
import ast
from copy import deepcopy
import os
from pathlib import Path
import subprocess
import sys
import pytest
from test_simulation_restart import certificate,sources,dump_program,sealed,storage,prepare
from services import simulation_restart as restart,portfolio_accounting as accounting

ROOT=Path(__file__).resolve().parents[1]


def test_startup_modules_and_render_have_no_restart_mutation_or_selector():
    modules=['app.py','scheduled_runner.py','autonomous_orchestrator.py','runtime_background.py',
             'scanner_worker.py','super_portfolio_worker.py','super_portfolio_jobs.py']
    for name in modules:
        tree=ast.parse((ROOT/name).read_text())
        for node in ast.walk(tree):
            if isinstance(node,(ast.Import,ast.ImportFrom)):
                text=ast.get_source_segment((ROOT/name).read_text(),node)
                assert 'simulation_restart' not in text and 'restart_trading' not in text,(name,text)
            if isinstance(node,ast.keyword):assert node.arg!='restart_context',name
    blueprint=(ROOT/'render.yaml').read_text()
    assert 'simulation_restart' not in blueprint and 'restart_context' not in blueprint
    assert 'ECONOMIC_PRODUCTION_ACTIVATION_ENABLED' not in blueprint


@pytest.mark.parametrize('environment',['development','production'])
def test_restart_drafts_unchanged_by_startup_imports_and_enable_flags(storage,sealed,environment):
    bundle=prepare(storage,sealed);key=restart._key(bundle['period_id'])
    before=storage.read_json(key)
    script="""
import json,sys
from services.storage_service import StorageService
from services import simulation_restart as restart,portfolio_accounting as accounting
import scheduled_runner,autonomous_orchestrator,runtime_background,scanner_worker,super_portfolio_worker,super_portfolio_jobs
storage=StorageService(sys.argv[1],database_url='',mode='local')
period=sys.argv[2];scoped=restart.AccountStorage(period,storage)
for family in accounting.FAMILIES:
 doc=scoped.read_json(accounting.key(family))
 assert doc['status']=='DRAFT'
 approval=dict(approved_by='TEST forbidden startup',approval_ref='NOT AUTHORIZED',family=family,
     opening_sha256=doc['opening_sha256'],start_at=doc['account']['created_at'],approved_at=doc['account']['created_at'],scope='production')
 try:accounting.approve(family,approval,storage=scoped)
 except ValueError:pass
 else:raise AssertionError('Automatic production/development activation succeeded')
assert all(a['status']=='DRAFT' for a in storage.read_json(restart._key(period))['accounts'].values())
print('All startup drafts unchanged')
"""
    env={**os.environ,'APP_ENVIRONMENT':environment,'APP_RUNTIME_ROOT':str(storage.base_dir/'startup-runtime'),
         'DATABASE_URL':'','AUTH_DATABASE_URL':'','STORAGE_MODE':'local','AUTH_STORAGE_MODE':'local',
         'RUNTIME_BACKGROUND_ENABLED':'false','REPORT_SCHEDULER_ENABLED':'false',
         'PAPER_TRADING_ENABLED':'false','ECONOMIC_PRODUCTION_ACTIVATION_ENABLED':'true'}
    result=subprocess.run([sys.executable,'-c',script,str(storage.base_dir),bundle['period_id']],env=env,cwd=ROOT,
                          capture_output=True,text=True,timeout=30)
    assert result.returncode==0,result.stderr[-2000:]
    assert storage.read_json(key)==before
