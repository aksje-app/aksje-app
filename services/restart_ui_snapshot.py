"""Small, dated UI read models. Trading never reads these projections.

One background read verifies the signed source and complete journal. Menu clicks
read only the small projection; full journals/exports remain available on demand.
"""
from copy import deepcopy
from datetime import datetime, timezone
import os
import time

from services import portfolio_accounting as ledger, production_restart as control
from services import simulation_restart as restart
from services.economic_opening import digest
from services.restart_reporting import _nav_history
from services.storage_service import get_storage_service

SCHEMA = 'VERIFIED_RESTART_UI_V1'
REFRESH_SECONDS = 60
_LAST_REQUEST = 0.0


def key(family):
    ledger.key(family)
    return 'ui/restart_snapshots/' + family + '.json'


def _build_model(bundle, family, pointer, approval):
    """Called only after full bundle, signed control and route verification."""
    doc = bundle['accounts'][family]
    report = ledger._report_verified(family, doc)
    period = report['new_period']
    history = _nav_history(period)
    latest = next((e['payload'] for e in reversed(doc['events']) if e['kind'] == 'STRATEGY_RUN'), {})
    verification = period['verification']
    meta = latest.get('state') or {}
    positions = {}
    for ticker, pos in period['positions'].items():
        positions[ticker] = {**deepcopy((meta.get('positions') or {}).get(ticker, {})), **deepcopy(pos), 'ticker': ticker, 'shares': pos['quantity'],
            'units': pos['quantity'], 'entry_price': pos.get('average_price'),
            'avg_price': pos.get('average_price'), 'market_data_at': pos['price_observed_at'],
            'market_value': verification['converted_position_values'].get(ticker)}
    presentation = {k:deepcopy(meta[k]) for k in ('vacancy_diagnostics', 'decision_confidence', 'portfolio_health') if k in meta}
    presentation['last_changes'] = deepcopy((meta.get('last_changes') or [])[-20:])
    presentation['history'] = deepcopy((meta.get('history') or [])[-12:])
    if verification['verified_nav']:
        presentation['vacancy_diagnostics'] = {**presentation.get('vacancy_diagnostics', {}), 'cash_pct': period['cash_nok']/verification['verified_nav']*100}
    projection = dict(**presentation, cash=period['cash_nok'], initial_cash=period['opening_nav_nok'],
        positions=positions, trades=deepcopy(period['trades'][-100:]),
        realized_pnl=period['realized_pnl_nok'], portfolio_value=verification['verified_nav'],
        portfolio_return_pct=verification['verified_net_return_pct'],
        economic_period_id=bundle['period_id'], economic_verification=verification,
        status='ACTIVE' if bundle['production_controls'][family]['status'] == 'RUNNING' else 'PAUSED',
        config=deepcopy(approval['settings']), updated_at=latest.get('at') or bundle['start_at'])
    compact_period = {k: deepcopy(v) for k, v in period.items() if k not in {'journal', 'trades'}}
    compact_period['trades'] = deepcopy(period['trades'][-100:])
    report = {**report, 'new_period': compact_period}
    data = dict(period_id=bundle['period_id'], family=family, start_at=bundle['start_at'],
        status='PRODUCTION_AUTHORIZED', archive=deepcopy(bundle['archive']),
        capital_kind=bundle['capital_kind'], learning_reset=False,
        legacy_positions_transferred=False,
        prior_learning='BEVART – EGEN STRATEGILÆRING, IKKE NYTT ØKONOMISK RESULTAT',
        historical_results=bundle['historical_results_label'], new_results=bundle['new_results_label'],
        account=report, nav_history=history[-1000:])
    model = dict(schema=SCHEMA, pointer=deepcopy(pointer), family=family,
        verified_at=datetime.now(timezone.utc).isoformat(timespec='seconds'),
        source_event_count=len(doc['events']), source_event_hash=doc['events'][-1]['hash'],
        source_control=bundle['production_controls'][family]['status'],
        approval_settings=deepcopy(approval['settings']), strategy_policy=approval['strategy_policy'],
        cost_policy=deepcopy(approval['cost_policy']), data=data, projection=projection,
        performance=_performance(period, history, bundle['period_id']),
        total_trades=len(period['trades']), total_nav_points=len(history),
        latest_run={k:deepcopy(latest[k]) for k in ('at', 'decisions') if k in latest},
        # Rich candidate inputs stay in the full journal, not the navigation payload.
        ranking=deepcopy(((latest.get('result') or {}).get('ranking') or [])[:100]))
    model['projection']['verified_at'] = model['verified_at']
    model['sha256'] = digest(model)
    return model


def publish(*, storage=None):
    """Read and verify once per selected period. Never writes a financial key."""
    started = time.monotonic()
    storage = storage or get_storage_service()
    if os.getenv('APP_ENVIRONMENT', 'production') == 'production' and os.getenv('NOK_DEPLOYMENT_ID'):
        control.require_backend(storage)
    groups = {}
    for family in restart.CAPITALS:
        pointer = storage.read_json(control.route_key(family), None)
        if pointer is None:
            continue
        if pointer.get('family') != family or pointer.get('deployment_id') != control.installation():
            raise ValueError('Selected UI account belongs to another installation')
        groups.setdefault(pointer['period_id'], []).append((family, pointer))
    published = []
    for period_id, selections in groups.items():
        bundle = storage.read_json(restart._key(period_id), None)
        restart.verify_bundle(bundle)
        if bundle['period_id'] != period_id:
            raise ValueError('UI source period mismatch')
        for family, pointer in selections:
            approval = control._check_record(bundle, family, running=False)
            if pointer.get('grant_sha256') != digest(bundle['production_controls'][family]['grant']):
                raise ValueError('UI route authorization mismatch')
            model = _build_model(bundle, family, pointer, approval)
            # A route switch during preparation must never publish an old account.
            if storage.read_json(control.route_key(family), None) != pointer:
                continue
            storage.write_json(key(family), model)
            published.append(family)
        del bundle
    return {'status': 'COMPLETED', 'families': published, 'seconds': round(time.monotonic()-started, 3)}


def request_refresh(*, storage=None):
    """Request scheduler refresh without loading a journal in the web process."""
    global _LAST_REQUEST
    now = time.monotonic()
    if _LAST_REQUEST and now - _LAST_REQUEST < 15:
        return
    storage = storage or get_storage_service()
    storage.write_json('ui/restart_snapshots/refresh_request.json', {
        'requested_at': datetime.now(timezone.utc).isoformat(timespec='seconds')})
    _LAST_REQUEST = now


def read(family, *, storage=None, refresh=True):
    """A missing/invalid projection stays explicitly pending; no legacy fallback."""
    storage = storage or get_storage_service()
    pointer = storage.read_json(control.route_key(family), None)
    if pointer is None:
        return None
    if pointer.get('family') != family or pointer.get('deployment_id') != control.installation():
        raise ValueError('Selected UI account belongs to another installation')
    model = storage.read_json(key(family), None)
    valid = isinstance(model, dict) and model.get('schema') == SCHEMA and model.get('pointer') == pointer
    if valid:
        valid = digest({k:v for k,v in model.items() if k != 'sha256'}) == model.get('sha256')
    age = float('inf')
    if valid:
        try:
            at = datetime.fromisoformat(model['verified_at'].replace('Z', '+00:00'))
            age = (datetime.now(timezone.utc) - at).total_seconds()
            valid = age >= 0
        except (KeyError, TypeError, ValueError):
            valid = False
    if refresh and (not valid or age >= REFRESH_SECONDS):
        request_refresh(storage=storage)
    if not valid:
        return {'loading': True, 'pointer': pointer, 'family': family}
    return {**model, 'loading': False, 'refreshing': age >= REFRESH_SECONDS}


def view(family, *, storage=None):
    model = read(family, storage=storage)
    if model is None:
        return None
    if model['loading']:
        return {'_loading': True, 'economic_period_id': model['pointer']['period_id'], 'positions': {}}
    return deepcopy(model['projection'])


def _performance(period, history, period_id):
    # All verified NAV points participate even when the chart is bounded.
    verified = period['verification']
    values = [1+r['net_return_pct']/100 for r in history if r['net_return_pct'] is not None]
    current = verified['verified_net_return_pct']
    unit = 1+current/100 if current is not None else None
    drawdown = max(0, (1-unit/max([1,unit]+values))*100) if unit is not None else None
    return dict(equity=verified['verified_nav'], cash=period['cash_nok'], total_return_pct=current,
        realized_pnl=period['realized_pnl_nok'], drawdown_pct=drawdown,
        open_positions=len(period['positions']), economic_period_id=period_id,
        economic_verification=verified, return_basis='DOCUMENTED_NOK_NET_UNITIZED_WHEN_FLOWS')


def metrics(family, *, storage=None):
    model = read(family, storage=storage)
    if model is None or model['loading']:
        return None
    return {**deepcopy(model['performance']), 'verified_at': model['verified_at']}
