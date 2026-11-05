"""Opt-in realistic monolith acceptance: retain all receipts and run the real engine.

RUN_RESTART_MEMORY_BUDGET=1 pytest -q -s tests/test_restart_large_bundle_budget.py
"""
import gc
import json
import os

import pytest
from test_restart_trading import active, evidence, at
from test_simulation_restart import certificate, sources, dump_program, sealed, storage, prepare
from services import portfolio_accounting as ledger, restart_trading as trading
from services.economic_opening import digest

pytestmark = pytest.mark.skipif(os.getenv('RUN_RESTART_MEMORY_BUDGET') != '1', reason='Explicit 92 MiB memory acceptance')


def test_full_monolith_cycle_preserves_receipts_under_2_gib(active):
    from dataclasses import asdict
    from autonomous_portfolio import AutonomousParameters
    from runtime_memory import release_process_memory, memory_snapshot
    backend, initial, _ = active
    key = trading.restart._key(initial['period_id'])
    bundle = backend.read_json(key)
    doc = bundle['accounts']['autonomy']
    when = at(active)
    template = [{'ticker': 'T'+str(i), 'score': 75.2, 'risk': 21.3,
                 'source': 'SYNTHETIC MEMORY ACCEPTANCE ONLY', 'detail': 'økonomisk historikk'} for i in range(150)]
    total = 0
    while total < 92 * 1024**2:
        run_id = 'historical-'+str(len(doc['events']))
        request = dict(period=bundle['period_id'],family='autonomy',run_id=run_id,at=when,strategy_input=template)
        payload = dict(run_id=run_id,request_sha256=digest(request),request=request,at=when,
                       period_id=bundle['period_id'],family='autonomy',state={},decisions=[],result={})
        ledger._append(doc,'STRATEGY_RUN',payload)
        total += len(json.dumps(doc['events'][-1],ensure_ascii=False))
    ledger.verify(doc)
    count = len(doc['events'])
    first_hash = doc['events'][0]['hash']
    backend.write_json(key,bundle)
    period = bundle['period_id']
    del bundle, doc, initial, template
    gc.collect()
    release_process_memory('before-large-monolith-acceptance')
    reference = trading.account_reference(period,'autonomy',storage=backend)
    result = trading.autonomy(period_id=period,run_id='memory-acceptance',at=when,
        evidence=evidence(when),parameters=asdict(AutonomousParameters()),candidates=[],
        account_ref=reference,storage=backend)
    measured = memory_snapshot()
    # Do not load a second complete bundle while the first remains reachable.
    saved = backend.read_json(key)['accounts']['autonomy']
    ledger.verify(saved)
    assert len(saved['events']) >= count + 1
    assert saved['events'][0]['hash'] == first_hash
    assert saved['events'][-1]['payload']['run_id'] == 'memory-acceptance'
    assert result['family'] == 'autonomy'
    assert measured['process_peak_rss_mb'] < 2048
    if measured.get('cgroup_memory_limit_mb', 99999) <= 2048:
        assert measured['cgroup_memory_peak_mb'] < 2048
    print(json.dumps({'synthetic_payload_mb': round(total/1024**2,1), 'preserved_events':count,
                      'memory':measured},ensure_ascii=False))
