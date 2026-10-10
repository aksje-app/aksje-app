from copy import deepcopy
from dataclasses import asdict
from datetime import datetime, timedelta, timezone
import pytest
import autonomous_portfolio as ap
import learning_runtime as lr
from learning_experiments import checksum


def frame(day=0, price=100, **changes):
    at = (datetime(2025, 1, 6, 12, tzinfo=timezone.utc) + timedelta(days=day)).isoformat()
    candidate = dict(ticker='ABC.OL', price=price, investment_score=85, risk_score=20,
        data_quality_score=90, sector='Technology', autonomy_outcome_code='KJØPSKANDIDAT',
        portfolio_action='BUY', valid_for_decision=True, evidence_valid_for_decision=True,
        final_decision_ready=True, price_timestamp=at)
    candidate.update(changes)
    value = dict(engine='AUTONOMY', run_id=str(day), at=at,
        config=asdict(ap.AutonomousParameters()), candidates=[candidate])
    value['sha256'] = checksum(value)
    return value


def no_io(monkeypatch):
    def fail(*args, **kwargs):
        pytest.fail('Simulation touched production I/O')
    for name in ('load_parameters', 'load_portfolio', 'load_learning_portfolio', '_write',
                 '_notification', '_record_trade', 'get_market_snapshot_service', 'get_strategy_account_service'):
        monkeypatch.setattr(ap, name, fail)
    monkeypatch.setattr(ap, 'durable_read_json', fail)


def test_real_autonomy_buy_stop_cooldown_and_frozen_clock(monkeypatch):
    no_io(monkeypatch)
    first = frame()
    original = deepcopy(first)
    state, equity, buys = lr.autonomy_step(first, {})
    assert len(buys) == 1 and buys[0]['action'] == 'BUY'
    assert buys[0]['timestamp'].startswith('2025-01-06')
    state, equity, sells = lr.autonomy_step(frame(1, 94), {}, state)
    assert sells[0]['action'] == 'SELL' and sells[0]['pnl'] < 0
    assert sells[0]['holding_days'] == 1
    state, equity, buys = lr.autonomy_step(frame(2, 100), {}, state)
    assert not buys and not state['portfolio']['positions']
    assert first == original
    assert ap._SIMULATION.get() is None


def test_missing_authorization_never_bought_and_sizing_caps(monkeypatch):
    no_io(monkeypatch)
    state, _, actions = lr.autonomy_step(frame(valid_for_decision=False), {})
    assert not actions
    state, _, actions = lr.autonomy_step(frame(), {'maximum_position_pct': .8})
    assert actions[0]['value'] <= 4000
    with pytest.raises(ValueError, match='Unsupported'):
        lr.autonomy_step(frame(), {'notify_trades': True})
    with pytest.raises(ValueError, match='bounds'):
        lr.autonomy_step(frame(), {'maximum_position_pct': -1})


def test_fee_sensitivity_and_early_loss_are_explicit(monkeypatch):
    no_io(monkeypatch)
    result = lr.replay_autonomy([frame(), frame(1, 94)], {})
    assert result['early_loss_count'] == 1
    assert result['transaction_cost'] > 0
    assert result['net_return_pct'] < result['gross_return_pct']
    assert not result['promotion_eligible']


def test_forward_not_backfill_restart_idempotent_and_frozen_reference(monkeypatch):
    no_io(monkeypatch)
    first = lr.process_forward_frame(frame())
    assert first['status'] == 'WAITING_NEW_DATA' and not first['accounts']
    later = frame(1)
    later['config']['minimum_investment_score'] = 99
    later['sha256'] = checksum({k:v for k,v in later.items() if k != 'sha256'})
    active = lr.process_forward_frame(later, first)
    assert active['status'] == 'ACTIVE_SHADOW' and len(active['accounts']) == 3
    assert active['accounts'][0]['trade_count'] == 1
    assert lr.process_forward_frame(later, active) == active
    assert lr.process_forward_frame(frame(), active) == active
    mutated = deepcopy(active); mutated['plan']['config']['minimum_investment_score'] = 0
    with pytest.raises(ValueError, match='mutated'):
        lr.process_forward_frame(frame(2), mutated)


class MemoryStorage:
    def __init__(self): self.rows = {}
    def read_json(self, key, default=None): return deepcopy(self.rows.get(key, default))
    def write_json_immutable(self, key, value): return self.rows.setdefault(key, deepcopy(value))
    def mutate_json(self, key, fn, default=None):
        value = fn(deepcopy(self.rows.get(key, default)))
        self.rows[key] = deepcopy(value)
        return value


def test_immutable_archive_budget_coverage_and_round_trip(monkeypatch):
    service = MemoryStorage(); monkeypatch.setattr(lr, 'storage', lambda: service)
    result = lr.archive(frame())
    record = service.rows[lr.INDEX]['records'][0]
    assert lr.load_frame(record)['candidates'] == frame()['candidates']
    assert lr.archive(frame()) == result
    assert lr.coverage()['engines']['AUTONOMY']['frames'] == 1
    monkeypatch.setattr(lr, 'MAX_ARCHIVE_BYTES', service.rows[lr.INDEX]['bytes'])
    assert lr.archive(frame(1))['status'] == 'STORAGE_BUDGET_REACHED'
    assert len(service.rows[lr.INDEX]['records']) == 1
    assert lr.coverage()['reported_gaps'] == 1
    assert all(k.startswith('controlled_learning/') for k in service.rows)


def test_future_nested_evidence_rejected():
    f = frame(raw={'official_events': [{'published_at': frame(1)['at']}]})
    with pytest.raises(ValueError, match='Future'):
        lr.validate(f)


def test_scheduled_job_resumes_future_data_and_never_old_archive(monkeypatch):
    service = MemoryStorage(); monkeypatch.setattr(lr, 'storage', lambda: service)
    no_io(monkeypatch)
    lr.archive(frame()); lr.archive(frame(1))
    lr.run_forward_batch()
    key = 'controlled_learning/forward/AUTONOMY.json'
    assert service.rows[key]['last_at'] == frame(1)['at'] and not service.rows[key]['accounts']
    lr.archive(frame(2))
    assert lr.run_forward_batch()['frames_processed'] == 1
    assert service.rows[key]['accounts'][0]['trade_count'] == 1
    assert lr.run_forward_batch()['frames_processed'] == 0


def test_profit_protection_uses_prior_peak_and_preserves_gains(monkeypatch):
    no_io(monkeypatch)
    state, _, _ = lr.autonomy_step(frame(), {})
    state, _, _ = lr.autonomy_step(frame(1, 105), {}, state)
    assert state['portfolio']['positions']['ABC.OL']['highest_price'] == 105
    state, _, sells = lr.autonomy_step(frame(2, 102), {}, state)
    assert sells and sells[0]['pnl'] > 0
    assert sells[0]['peak_gain_pct'] == pytest.approx(5)
    assert sells[0]['effective_stop_price'] > 100


def test_sector_slots_and_reserve_are_production_constraints(monkeypatch):
    no_io(monkeypatch)
    f = frame()
    f['candidates'] += [dict(f['candidates'][0], ticker=f'T{i}.OL') for i in range(40)]
    f['sha256'] = checksum({k:v for k,v in f.items() if k != 'sha256'})
    state, equity, buys = lr.autonomy_step(f, {'maximum_open_positions': 2})
    assert len(state['portfolio']['positions']) == len(buys) == 2
    assert state['portfolio']['cash'] >= equity * .1
    state, equity, buys = lr.autonomy_step(f, {'maximum_sector_pct': 5})
    assert sum(p['quantity'] * p['last_price'] for p in state['portfolio']['positions'].values()) <= equity * .05


def test_thread_context_is_released_on_engine_exception(monkeypatch):
    monkeypatch.setattr(ap, 'run_autonomous_cycle', lambda *a, **kw: (_ for _ in ()).throw(RuntimeError('forced')))
    with pytest.raises(RuntimeError, match='forced'):
        ap.simulate_autonomy_cycle([], parameters=frame()['config'], portfolio={}, trades=[],
            now=datetime.fromisoformat(frame()['at']), run_id='error')
    assert ap._SIMULATION.get() is None


def test_legacy_import_never_arms_forward(monkeypatch):
    service = MemoryStorage(); monkeypatch.setattr(lr, 'storage', lambda: service)
    f = frame(); f['source_manifest'] = {'origin': 'old'}
    lr.archive(f)
    lr.run_forward_batch()
    assert service.rows.get('controlled_learning/forward/AUTONOMY.json') is None


def test_scheduler_memory_and_timeout_do_not_interrupt_trading(monkeypatch):
    import learning_shadow_scheduler as scheduler
    import subprocess
    monkeypatch.setattr(ap, '_available_memory_mb', lambda: 100)
    assert scheduler.run_shadow_job()['status'] == 'DEFERRED_MEMORY'
    monkeypatch.setattr(ap, '_available_memory_mb', lambda: 1000)
    monkeypatch.setattr(scheduler.subprocess, 'run', lambda *a, **kw: (_ for _ in ()).throw(subprocess.TimeoutExpired('worker', 50)))
    assert scheduler.run_shadow_job()['status'] == 'DEFERRED_TIMEOUT'


def test_verified_backfill_accepts_originals_and_rejects_tampering(monkeypatch):
    from replay_contract import build_snapshot
    service = MemoryStorage(); monkeypatch.setattr(lr, 'storage', lambda: service)
    candidate = frame()['candidates'][0] | {'liquidity_score': 80, 'mission_eligible': True, 'strategy_matches': ['Quality']}
    portfolio = {'status': 'ACTIVE', 'cash': 500000, 'positions': {}}
    bundle = build_snapshot(run_id='VERIFIED-OLD', candidates=[candidate],
        portfolio_before=portfolio, portfolio_after=portfolio,
        portfolio_context={'portfolio_status': 'ACTIVE', 'limits': {'max_positions': 20}},
        parameters=frame()['config'], market_snapshot={'snapshot_id': 'OLD'}, actions=[])
    assert bundle['manifest']['audit']['ok']
    assert lr.import_replay_bundle(bundle)['status'] == 'CAPTURED'
    restored = lr.load_frame(service.rows[lr.INDEX]['records'][0])
    assert restored['scope'].startswith('LEGACY_FINAL_INPUT')
    assert restored['source_manifest']['hashes'] == bundle['manifest']['hashes']
    bundle['files']['candidates_input.json'][0]['price'] = 999
    with pytest.raises(ValueError, match='CHECKSUM'):
        lr.import_replay_bundle(bundle)


def test_real_worker_memory_cap_isolation_and_persisted_restart(monkeypatch, tmp_path):
    import os
    import subprocess
    import sys
    from pathlib import Path
    from services.storage_service import StorageService
    service = StorageService(tmp_path / 'data/services', database_url='', mode='local')
    monkeypatch.setattr(lr, 'storage', lambda: service)
    lr.archive(frame())
    env = {**os.environ, 'APP_RUNTIME_ROOT': str(tmp_path), 'STORAGE_MODE': 'local',
           'DATABASE_URL': '', 'OPENBLAS_NUM_THREADS': '1', 'OMP_NUM_THREADS': '1'}
    worker = Path(__file__).resolve().parents[1] / 'tools/learning_shadow_worker.py'
    def run():
        result = subprocess.run([sys.executable, str(worker)], env=env, capture_output=True, text=True, timeout=50)
        assert result.returncode == 0, result.stderr[-1000:]
    run()
    lr.archive(frame(1))
    run()
    saved = service.read_json('controlled_learning/forward/AUTONOMY.json')
    assert saved['status'] == 'ACTIVE_SHADOW' and saved['accounts'][0]['trade_count'] == 1
    run()
    assert service.read_json('controlled_learning/forward/AUTONOMY.json') == saved
    # The child has created no ordinary portfolio or trade storage documents.
    assert not (tmp_path / 'data/autonomous_portfolio/portfolio.json').exists()


def test_disk_backed_search_validates_manifest_and_chronological_splits(tmp_path):
    import gzip
    import json
    from learning_dataset import FrameDataset
    from learning_experiments import chronological_split, run_search
    records = []
    for i in range(20):
        f = frame(i)
        name = f'{i}.json.gz'
        with gzip.open(tmp_path / name, 'wt') as handle:
            json.dump(f, handle)
        records.append({'file': name, 'sha256': f['sha256'], 'at': f['at']})
    manifest = {'frames': records, 'sha256': checksum(records)}
    (tmp_path / 'manifest.json').write_text(json.dumps(manifest))
    data = FrameDataset(tmp_path)
    train, validation, holdout = chronological_split(data, embargo_days=0)
    assert isinstance(train, FrameDataset) and len(train) == 12
    assert len(validation) == len(holdout) == 4
    result = run_search(data, {'minimum_investment_score': [73, 75]}, budget=2, embargo_days=0)
    assert result['trial_count'] == 2 and not result['production_approval_available']
    manifest['frames'].pop()
    (tmp_path / 'manifest.json').write_text(json.dumps(manifest))
    with pytest.raises(ValueError, match='manifest checksum'):
        FrameDataset(tmp_path)


def test_sp_forward_early_loss_uses_recorded_entry_date(monkeypatch):
    import super_portfolio as sp
    from tests.test_program_audit_candidate_fallback import candidate
    def make(i, price):
        at = frame(i)['at']
        row = candidate('AAA'); row['price'] = price; row['raw']['last_price'] = price
        value = {'engine': 'SUPER_PORTFOLIO', 'at': at, 'run_id': str(i),
            'config': asdict(sp.SuperPortfolioConfig()),
            'pipeline': {'run_id': str(i), 'created_at': at, 'candidates': [row],
                         'market_activation_levels': {'USA': 'PRODUCTION'}}}
        value['config'].update(target_positions=1, production_market_scopes=['USA'])
        value['sha256'] = checksum(value)
        return value
    state = lr.process_forward_frame(make(0, 105))
    for i in range(1, 4):
        state = lr.process_forward_frame(make(i, 105 if i < 3 else 95), state)
    baseline = state['accounts'][0]
    assert baseline['early_loss_count'] == baseline['early_loss_measured_exits'] == 1
    assert baseline['closed_pnl'] is None
    assert baseline['costs'] > 0
