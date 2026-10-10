"""Immutable point-in-time archive and paired, incremental shadow accounts.

Only controlled_learning/* is writable here. Capture never discards old frames
silently: the fixed storage budget stops collection and reports the gap.
"""
from copy import deepcopy
from dataclasses import asdict
from datetime import datetime, timezone
import base64
import gzip
import json
from learning_experiments import checksum

PREFIX = 'controlled_learning/history/'
INDEX = PREFIX + 'index.json'
MAX_ARCHIVE_BYTES = 128 * 1024 * 1024
MAX_FRAME_BYTES = 8 * 1024 * 1024
MAX_RECORDS = 20000
AUTONOMY_PARAMETERS = {'minimum_investment_score', 'minimum_data_quality', 'maximum_risk_score',
    'maximum_position_pct', 'maximum_sector_pct', 'maximum_open_positions', 'reserve_cash_pct',
    'stop_loss_pct', 'trailing_stop_pct', 'take_profit_pct', 'score_exit_threshold',
    'reentry_cooldown_days', 'stagnation_days', 'stagnation_band_pct', 'cash_review_days',
    'cash_review_max_return_pct'}


def storage():
    from services.storage_service import get_storage_service
    return get_storage_service()


def validate(frame):
    if checksum({k:v for k,v in frame.items() if k != 'sha256'}) != frame.get('sha256'):
        raise ValueError('Frame checksum mismatch')
    at = datetime.fromisoformat(frame['at'].replace('Z', '+00:00'))
    if at.tzinfo is None or not frame.get('config'):
        raise ValueError('Missing frozen clock/configuration')
    def walk(value):
        if isinstance(value, dict):
            for key, child in value.items():
                if key in {'price_timestamp', 'data_timestamp', 'published_at', 'observed_at'} and child:
                    stamp = datetime.fromisoformat(str(child).replace('Z', '+00:00'))
                    if stamp.tzinfo is None or stamp > at:
                        raise ValueError('Future or undated evidence')
                elif isinstance(child, (dict, list)):
                    walk(child)
        elif isinstance(value, list):
            for child in value:
                walk(child)
    walk(frame.get('candidates', []))
    walk(frame.get('pipeline', {}))
    walk(frame.get('universe', []))
    walk(frame.get('deep_candidates', []))
    return at


def archive(frame):
    frame = deepcopy(frame)
    frame.setdefault('schema', 1)
    frame.setdefault('at', datetime.now(timezone.utc).isoformat())
    frame['sha256'] = checksum({k:v for k,v in frame.items() if k != 'sha256'})
    validate(frame)
    raw = json.dumps(frame, ensure_ascii=False, sort_keys=True, separators=(',', ':'), default=str).encode()
    if len(raw) > MAX_FRAME_BYTES:
        raise ValueError('Historical frame exceeds 8 MiB budget')
    packed = {'sha256': frame['sha256'], 'gzip_base64': base64.b64encode(gzip.compress(raw, mtime=0)).decode()}
    size = len(json.dumps(packed).encode())
    identity = checksum([frame['engine'], frame['run_id']])
    key = PREFIX + identity + '.json'
    def reserve(current):
        current = deepcopy(current or {'records': [], 'bytes': 0, 'gaps': 0})
        existing = next((r for r in current['records'] if r['key'] == key), None)
        if existing:
            if existing['sha256'] != frame['sha256']:
                raise ValueError('Historical run identity conflict')
            return current
        if current['bytes'] + size > MAX_ARCHIVE_BYTES or len(current['records']) >= MAX_RECORDS:
            current.update(status='STORAGE_BUDGET_REACHED', gaps=current.get('gaps', 0) + 1)
            return current
        current['records'].append({'key': key, 'sha256': frame['sha256'], 'bytes': size,
            'engine': frame['engine'], 'at': frame['at'], 'status': 'PENDING',
            'complete_universe': bool(frame.get('complete_universe')),
            'legacy_import': bool(frame.get('source_manifest'))})
        current['bytes'] += size
        return current
    service = storage()
    index = service.mutate_json(INDEX, reserve)
    if not any(r['key'] == key for r in index['records']):
        return {'status': 'STORAGE_BUDGET_REACHED', 'production_changed': False}
    stored = service.write_json_immutable(key, packed)
    if stored != packed:
        raise ValueError('Immutable historical frame conflict')
    def finalize(current):
        for row in current['records']:
            if row['key'] == key:
                row['status'] = 'READY'
        return current
    service.mutate_json(INDEX, finalize)
    return {'status': 'CAPTURED', 'key': key, 'sha256': frame['sha256'], 'production_changed': False}


def load_frame(record):
    packed = storage().read_json(record['key'])
    compressed = base64.b64decode(packed['gzip_base64'], validate=True)
    # Decompression bomb protection, including imported documents.
    import io
    with gzip.GzipFile(fileobj=io.BytesIO(compressed)) as stream:
        raw = stream.read(MAX_FRAME_BYTES + 1)
    if len(raw) > MAX_FRAME_BYTES:
        raise ValueError('Decompressed frame exceeds budget')
    frame = json.loads(raw)
    if frame['sha256'] != record['sha256']:
        raise ValueError('Archive checksum mismatch')
    validate(frame)
    return frame


def capture_autonomy(candidates, *, parameters, run_id, portfolio_before):
    return archive({'engine': 'AUTONOMY', 'run_id': run_id, 'config': parameters,
        'candidates': deepcopy(list(candidates)), 'portfolio_before': deepcopy(portfolio_before),
        'scope': 'FINAL_PRODUCTION_INPUT_WITH_ALL_GATES', 'complete_universe': False,
        'accounting': 'PRODUCTION_MARKS_GROSS_OF_FEES'})


def coverage():
    index = storage().read_json(INDEX, {}) or {}
    ready = [r for r in index.get('records', []) if r['status'] == 'READY']
    return {'archive_bytes': index.get('bytes', 0), 'budget_bytes': MAX_ARCHIVE_BYTES,
        'reported_gaps': index.get('gaps', 0), 'status': index.get('status', 'COLLECTING'),
        'engines': {engine: {'frames': len(rows), 'first_at': min((r['at'] for r in rows), default=None),
            'last_at': max((r['at'] for r in rows), default=None),
            'whole_universe_frames': sum(r['complete_universe'] for r in rows),
            'historical_completeness': 'UNPROVEN_NO_RETROACTIVE_RECONSTRUCTION'}
            for engine in ('AUTONOMY', 'SUPER_PORTFOLIO', 'AUTONOMY_UNIVERSE')
            for rows in [[r for r in ready if r['engine'] == engine]]},
        'production_changed': False}


def autonomy_step(frame, parameters, state=None):
    from autonomous_portfolio import AutonomousParameters, default_portfolio, simulate_autonomy_cycle, portfolio_equity
    if set(parameters) - AUTONOMY_PARAMETERS:
        raise ValueError('Unsupported Autonomy experiment parameter')
    config = {**frame['config'], **parameters}
    params = AutonomousParameters(**config).normalized()
    if asdict(params) != config:
        # Do not silently normalize invalid trials into different experiments.
        raise ValueError('Autonomy parameters outside normalized bounds')
    state = deepcopy(state or {})
    portfolio = state.get('portfolio') or default_portfolio(params)
    if not state:
        portfolio.update(status='ACTIVE', pause_reason='')
    result = simulate_autonomy_cycle(frame['candidates'], parameters=config, portfolio=portfolio,
        trades=state.get('trade_history', []), now=validate(frame), run_id=frame['run_id'])
    if not result['execution_integrity']['ok']:
        raise ValueError('Autonomy simulation integrity failed')
    return {'portfolio': result['portfolio'], 'trade_history': result['trade_history']}, portfolio_equity(result['portfolio']), result['trades']


def replay_autonomy(frames, parameters):
    state, initial, peak, drawdown, turnover = None, None, 0., 0., 0.
    trades, cash = [], []
    previous = None
    for frame in frames:
        at = validate(frame)
        if frame['engine'] != 'AUTONOMY' or (previous and at <= previous):
            raise ValueError('Autonomy requires increasing frozen frames')
        previous = at
        state, equity, actions = autonomy_step(frame, parameters, state)
        initial = initial or state['portfolio']['initial_cash']
        peak = max(peak, initial, equity)
        drawdown = max(drawdown, 100 * (peak - equity) / peak)
        turnover += sum(t['value'] for t in actions)
        trades.extend(actions)
        cash.append(100 * state['portfolio']['cash'] / equity)
    if initial is None:
        raise ValueError('No Autonomy historical frames')
    # Fees are an explicit sensitivity metric, not fabricated production fills.
    fee_estimate = turnover * .002
    sales = [t for t in trades if t['action'] in {'SELL', 'SELL_PARTIAL'}]
    return {'net_return_pct': 100 * ((equity - fee_estimate) / initial - 1),
        'gross_return_pct': 100 * (equity / initial - 1), 'maximum_drawdown_pct': drawdown,
        'transaction_cost': fee_estimate, 'cost_model': '0.2_PERCENT_TURNOVER_SENSITIVITY', 'drawdown_basis': 'GROSS_MARKS',
        'trade_count': len(trades), 'mean_cash_pct': sum(cash) / len(cash),
        'early_loss_count': sum(t['pnl'] < 0 and t['holding_days'] < 3 for t in sales),
        'losing_exit_count': sum(t['pnl'] < 0 for t in sales), 'measured_exit_count': len(sales),
        'production_changed': False, 'promotion_eligible': False,
        'fill_model': 'PRODUCTION_MARKS_GROSS_OF_FEES', 'upstream_research_recomputed': False}


def _step(frame, parameters, state):
    if frame['engine'] == 'AUTONOMY':
        return autonomy_step(frame, parameters, state)
    from super_portfolio import default_state, evaluate
    state = deepcopy(state or default_state())
    state['config'] = {**frame['config'], **parameters, 'auto_pushover': False}
    if not state.get('last_full_assessment_at'):
        state['initial_cash'] = state['config']['start_cash']
        state['portfolio_value'] = state['initial_cash']
    previous = deepcopy(state.get('positions') or {})
    result = evaluate(pipeline=deepcopy(frame['pipeline']), simulation_state=state,
        persist=False, now=validate(frame), rebalance_policy='AUTO')
    changes = deepcopy(result.get('changes', []))
    at = validate(frame)
    for trade in changes:
        position = previous.get(trade.get('ticker'), {})
        if trade.get('action') == 'SELL' and position.get('entry_date'):
            opened = datetime.fromisoformat(position['entry_date'].replace('Z', '+00:00'))
            from datetime import timedelta
            cursor, count = opened.date(), 0
            while cursor <= at.date():
                count += cursor.weekday() < 5
                cursor += timedelta(days=1)
            trade['holding_days'] = max(0, count - 1)
    return result['state'], result['state']['portfolio_value'], changes


def process_forward_frame(frame, current=None):
    """Pure, restartable transition; hypotheses fixed before first tested frame."""
    validate(frame)
    current = deepcopy(current or {})
    if not current:
        key = 'minimum_investment_score' if frame['engine'] == 'AUTONOMY' else 'minimum_score'
        reference = float(frame['config'][key])
        plan = {'engine': frame['engine'], 'started_at': frame['at'], 'config': deepcopy(frame['config']),
            'variants': [{}, {key: max(0, reference - 2)}, {key: min(100, reference + 2)}],
            'hypothesis': 'PRE_REGISTERED_THRESHOLD_SENSITIVITY_NOT_HISTORICAL_WINNERS'}
        return {'plan': plan, 'plan_sha256': checksum(plan), 'status': 'WAITING_NEW_DATA',
            'last_at': frame['at'], 'last_frame_sha256': frame['sha256'], 'accounts': [],
            'dates': [], 'production_changed': False, 'validated': False}
    if checksum(current['plan']) != current['plan_sha256'] or frame['engine'] != current['plan']['engine']:
        raise ValueError('Forward plan mutated or engine mismatch')
    if frame['at'] <= current['last_at']:
        if frame['at'] == current['last_at'] and frame['sha256'] != current['last_frame_sha256']:
            raise ValueError('Conflicting forward observation')
        return current
    paired = deepcopy(frame)
    paired['config'] = deepcopy(current['plan']['config'])
    paired['sha256'] = checksum({k:v for k,v in paired.items() if k != 'sha256'})
    accounts = []
    for i, params in enumerate(current['plan']['variants']):
        old = current['accounts'][i] if current['accounts'] else {}
        state, equity, trades = _step(paired, params, old.get('state'))
        initial = float(current['plan']['config'].get('initial_cash', current['plan']['config'].get('start_cash')))
        peak = max(old.get('peak', initial), equity)
        costs = old.get('costs', 0.) + (sum(t.get('value', 0) for t in trades) * .002 if frame['engine'] == 'AUTONOMY' else float(state.get('last_portfolio_transaction_cost') or 0))
        sales = [t for t in trades if t.get('action') in {'SELL', 'SELL_PARTIAL'}]
        accounts.append({'parameters': params, 'state': state, 'equity': equity, 'peak': peak,
            'maximum_drawdown_pct': max(old.get('maximum_drawdown_pct', 0), 100 * (peak - equity) / peak),
            'costs': costs, 'net_return_pct': 100 * ((equity - costs if frame['engine'] == 'AUTONOMY' else equity) / initial - 1),
            'trade_count': old.get('trade_count', 0) + len(trades),
            'early_loss_count': old.get('early_loss_count', 0) + sum((t.get('pnl_pct') or 0) < 0 and t.get('holding_days', 999) < 3 for t in sales),
            'cash_pct': (100 * state['portfolio']['cash'] / equity if frame['engine'] == 'AUTONOMY' else float((state.get('vacancy_diagnostics') or {}).get('cash_pct', 100))),
            'closed_pnl': (old.get('closed_pnl', 0) + sum(t.get('pnl', 0) for t in sales) if frame['engine'] == 'AUTONOMY' else None),
            'early_loss_measured_exits': old.get('early_loss_measured_exits', 0) + sum(t.get('pnl_pct') is not None and t.get('holding_days') is not None for t in sales),
            'exits': old.get('exits', 0) + len(sales),
            'peak_gain_sum_pct': old.get('peak_gain_sum_pct', 0) + sum(t.get('peak_gain_pct') or 0 for t in sales),
            'retained_gain_sum_pct': old.get('retained_gain_sum_pct', 0) + sum(max(0, t.get('pnl_pct') or 0) for t in sales if t.get('peak_gain_pct') is not None),
            'retention_measured_exits': old.get('retention_measured_exits', 0) + sum(t.get('peak_gain_pct') is not None for t in sales)})
    dates = sorted(set(current['dates'] + ([frame['at'][:10]] if validate(frame).weekday() < 5 else [])))
    if len(json.dumps(accounts, default=str).encode()) > 8 * 1024**2:
        raise ValueError('Forward state exceeds 8 MiB budget; export before continuation')
    current.update(accounts=accounts, dates=dates, status='ACTIVE_SHADOW', last_at=frame['at'],
        last_frame_sha256=frame['sha256'], observed_trading_dates=len(dates),
        measurement_20_days=len(dates) >= 20, matured_60_days=len(dates) >= 60,
        production_approval_available=False)
    return current


def run_forward_batch(limit=6):
    """Bounded optional scheduler job. Each committed frame resumes exactly once."""
    service = storage()
    index = service.read_json(INDEX, {}) or {}
    done = 0
    for engine in ('AUTONOMY', 'SUPER_PORTFOLIO'):
        key = 'controlled_learning/forward/' + engine + '.json'
        current = service.read_json(key, {}) or {}
        # Arm on the latest available frame, never label old archive data forward.
        rows = sorted([r for r in index.get('records', []) if r['engine'] == engine and r['status'] == 'READY' and not r.get('legacy_import')], key=lambda r:r['at'])
        if not current and rows:
            frame = load_frame(rows[-1])
            service.mutate_json(key, lambda value: value or process_forward_frame(frame))
            continue
        for record in [r for r in rows if r['at'] > current.get('last_at', '')][:max(1, min(6, limit))]:
            frame = load_frame(record)
            current = service.mutate_json(key, lambda value: process_forward_frame(frame, value))
            done += 1
    return {'status': 'COMPLETED', 'frames_processed': done, 'coverage': coverage(),
        'production_changed': False, 'validated': False}


def import_replay_bundle(bundle):
    """Preserve real legacy inputs; do not claim old engines or universe replay."""
    from replay_contract import audit_snapshot
    audit = audit_snapshot(bundle, rerun=False)
    if not audit['ok']:
        raise ValueError('Historical replay contract invalid: ' + '; '.join(audit['errors']))
    manifest, files = bundle['manifest'], bundle['files']
    frame = {'engine': 'AUTONOMY', 'run_id': 'LEGACY-' + manifest['run_id'],
        'at': manifest['created_at'], 'config': files['configuration.json']['parameters'],
        'candidates': files['candidates_input.json'], 'portfolio_before': files['portfolio_before.json'],
        'recorded_actions': files['actions.json'], 'recorded_portfolio_after': files['portfolio_after.json'],
        'source_manifest': manifest, 'source_version': manifest['app_version'],
        'scope': 'LEGACY_FINAL_INPUT_ONLY_CURRENT_ENGINE_COUNTERFACTUAL', 'complete_universe': False,
        'prior_trade_history_complete': False}
    return archive(frame)


def backfill_legacy_batch(limit=2):
    """Read exact existing replay documents, bounded and restartable; never delete."""
    from replay_contract import REQUIRED_FILES
    service = storage()
    source = service.read_json('full_replay/index.json', []) or []
    key = 'controlled_learning/history/backfill.json'
    progress = service.read_json(key, {}) or {'processed': {}, 'source_count': len(source)}
    pending = [r for r in source if r.get('run_id') not in progress['processed']]
    for row in pending[:max(1, min(2, limit))]:
        rid = row['run_id']
        try:
            manifest = service.read_json(f'full_replay/{rid}/run_manifest.json', {})
            files = {name: service.read_json(f'full_replay/{rid}/{name}') for name in REQUIRED_FILES}
            result = import_replay_bundle({'manifest': manifest, 'files': files})
        except Exception as exc:
            result = {'status': 'REJECTED_INCOMPLETE_HISTORY', 'error': str(exc)[:300]}
        def commit(current):
            current = current or {'processed': {}, 'source_count': len(source)}
            current['processed'][rid] = result
            current['source_count'] = len(source)
            return current
        progress = service.mutate_json(key, commit)
        if result['status'] == 'STORAGE_BUDGET_REACHED':
            break
    return {'source_count': len(source), 'processed': len(progress['processed']),
        'captured': sum(r['status'] == 'CAPTURED' for r in progress['processed'].values()),
        'rejected': sum(r['status'] != 'CAPTURED' for r in progress['processed'].values()),
        'production_changed': False}
