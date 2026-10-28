"""Honest, order-free readiness for an EMPTY NOK simulation account.

This is not live_preview and never calls a provider, strategy runner or ledger
mutation. Execution still goes through the existing timed price/FX barriers.
"""
from copy import deepcopy
from datetime import datetime, timezone
from services.economic_opening import digest
from services.economic_ledger import stamp

SCHEMA = 'NOK_ACTIVATION_PREFLIGHT_V1'
MODE = 'ACTIVATION_PREFLIGHT_NO_ORDERS_NO_MARKET_RUN'
EXECUTION_POLICY = dict(price_max_age_seconds=900, fx_max_age_seconds=900,
                        missing_evidence='NO_EXECUTION', slippage='EXECUTION_PRICE_ONLY')


def frozen_market_policy(pipeline):
    """Freeze authoritative levels in memory; preserve any stricter old levels."""
    from market_universe import MARKET_ACTIVATION_LEVELS
    canonical = deepcopy(MARKET_ACTIVATION_LEVELS)
    frozen = pipeline.get('market_activation_levels')
    if frozen is None:
        return canonical
    if not isinstance(frozen, dict):
        raise ValueError('Invalid frozen market activation policy')
    levels = {'OFF': 0, 'SHADOW': 1, 'PRODUCTION': 2}
    old = {str(k).upper(): str(v).upper() for k, v in frozen.items()}
    if len(old) != len(frozen) or any(v not in levels for v in old.values()):
        raise ValueError('Invalid frozen market activation policy')
    known = {k.upper() for k in canonical}
    if set(old) - known:
        raise ValueError('Unknown frozen market scope')
    result = {}
    for market, current in canonical.items():
        prior = old.get(market.upper(), 'OFF')
        if levels[prior] > levels[current]:
            raise ValueError('Frozen market activation levels differ from governed production policy')
        result[market] = prior
    return result


def _bindings(period, family, settings, cost_policy, restore_review, storage):
    from services import production_restart as control, simulation_restart as restart
    from services.production_routing import strategy_settings
    from services.trading_costs import validate_family
    control.require_backend(storage)
    bundle = storage.read_json(restart._key(period))
    restart.verify_bundle(bundle)
    if family not in restart.CAPITALS:
        raise ValueError('Unknown account family')
    doc = bundle['accounts'][family]
    account = doc['account']
    if (account['initial_cash'] != restart.CAPITALS[family] or account['cash'] != restart.CAPITALS[family]
            or account['positions'] or account['trades']):
        raise ValueError('Activation preflight requires the existing empty account and exact capital')
    if digest(settings) != digest(strategy_settings(family, storage=storage, require_stored=True)):
        raise ValueError('Stored strategy settings changed')
    validate_family(cost_policy, family, settings)
    if (restore_review.get('status') != 'RESTORED_AND_VERIFIED'
            or restore_review.get('archive') != bundle['archive']
            or restore_review.get('review_sha256') != digest({k:v for k,v in restore_review.items() if k != 'review_sha256'})):
        raise ValueError('Matching original physical restore proof required')
    return bundle, doc, dict(period_id=period, family=family, deployment_id=control.installation(),
        capital_nok=restart.CAPITALS[family], opening_sha256=doc['opening_sha256'],
        start_at=bundle['start_at'], archive=deepcopy(bundle['archive']),
        restore_review_sha256=restore_review['review_sha256'], settings_sha256=digest(settings),
        cost_policy_sha256=digest(cost_policy), execution_policy=deepcopy(EXECUTION_POLICY))


def inspect(period, family, *, settings, cost_policy, restore_review, strategy_input, storage, at=None,
            runtime_evidence=None):
    """Return a truthful readiness receipt, even with zero current quotes/candidates."""
    bundle, doc, fields = _bindings(period, family, settings, cost_policy, restore_review, storage)
    if doc['status'] != 'DRAFT' or doc.get('approval') is not None:
        raise ValueError('Preflight only prepares the existing DRAFT account')
    if storage.read_json('simulation_restarts/routes/'+family+'.json', None) is not None:
        raise ValueError('Existing route must not be replaced')
    if family == 'super_portfolio':
        if not isinstance(strategy_input, dict) or not strategy_input.get('run_id'):
            raise ValueError('Actual independent Super Portfolio pipeline required')
        if any(r.get('source') != 'Super Portfolio independent market universe' for r in strategy_input.get('candidates', [])):
            raise ValueError('Independent Super Portfolio universe required')
        market_policy = frozen_market_policy(strategy_input)
    else:
        if not isinstance(strategy_input, list):
            raise ValueError('Actual saved strategy inputs required')
        market_policy = frozen_market_policy({})
    observed_at = at or datetime.now(timezone.utc).isoformat()
    stamp(observed_at)
    receipt = dict(schema=SCHEMA, mode=MODE, environment='production', at=observed_at, **fields,
        strategy_input_sha256=digest(strategy_input), market_activation_levels=market_policy,
        market_policy_source='market_universe.MARKET_ACTIVATION_LEVELS',
        runtime_evidence=deepcopy(runtime_evidence or {}),
        actual_market_run_performed=False, quotes_obtained=False, orders_created=0,
        persistent_writes_performed=False, account_status='DRAFT', ready_for_personal_B=True)
    receipt['receipt_sha256'] = digest(receipt)
    return receipt


def validate(receipt, period, family, *, settings, cost_policy, restore_review, storage):
    """Revalidate signed readiness; no quote exemption is granted to execution."""
    if (not isinstance(receipt, dict) or receipt.get('schema') != SCHEMA or receipt.get('mode') != MODE
            or receipt.get('receipt_sha256') != digest({k:v for k,v in receipt.items() if k != 'receipt_sha256'})
            or receipt.get('ready_for_personal_B') is not True
            or receipt.get('actual_market_run_performed') is not False
            or receipt.get('quotes_obtained') is not False or receipt.get('orders_created') != 0
            or receipt.get('persistent_writes_performed') is not False or receipt.get('environment') != 'production'):
        raise ValueError('Invalid signed activation preflight')
    stamp(receipt['at'])
    _, _, expected = _bindings(period, family, settings, cost_policy, restore_review, storage)
    if any(receipt.get(k) != v for k,v in expected.items()):
        raise ValueError('Activation preflight bindings changed')
    # A policy may remain stricter than current governance; promotion is never implicit.
    if frozen_market_policy({'market_activation_levels': receipt['market_activation_levels']}) != receipt['market_activation_levels']:
        raise ValueError('Signed market policy changed')
    return receipt
