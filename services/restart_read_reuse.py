"""Run-scoped reuse of detached account views, never of trading selections.

Every hit checks PostgreSQL row versions (including the route) without fetching
payloads. A financial/control write in *any* process invalidates the view. Full
signed/journal validation remains mandatory on misses and inside transactions.
No bundle/journal is retained by this cache and no durable data is changed.
"""
from contextlib import contextmanager
from contextvars import ContextVar
from copy import deepcopy
from functools import wraps
from datetime import datetime, timedelta, timezone
import json
import os

_SCOPE = ContextVar('restart_account_read_reuse', default=None)
_READ = ContextVar('restart_account_read_source', default=None)
MAX_BYTES = 8 * 1024**2


def _valuation_deadline(value):
    """Never reuse a NAV across its existing five-day evidence ceiling."""
    if not value or (value.get('economic_verification') or {}).get('status') != 'BESTÅTT':
        return None
    deadlines = []
    for position in value.get('positions', {}).values():
        stamps = [position.get('price_observed_at') or position.get('market_data_at')]
        if position.get('currency') != value.get('base_currency'):
            stamps.append((position.get('fx_quote') or {}).get('observed_at'))
        for stamp in stamps:
            try:
                at = datetime.fromisoformat(stamp.replace('Z', '+00:00'))
                if at.tzinfo is None:
                    return None
                deadlines.append((at + timedelta(days=5)).timestamp())
            except (ValueError, TypeError, AttributeError):
                return None
    return min(deadlines, default=float('inf'))


@contextmanager
def scope():
    if _SCOPE.get() is not None:
        yield
        return
    token = _SCOPE.set({})
    try:
        yield
    finally:
        _SCOPE.reset(token)


def scoped(fn):
    @wraps(fn)
    def call(*args, **kwargs):
        with scope():
            return fn(*args, **kwargs)
    return call


def _version(storage, family):
    from services import production_restart as control, simulation_restart as restart
    # Local/test adapters continue through the original fully verified path.
    if not hasattr(storage, 'json_row_versions') or not storage.using_postgres():
        return None
    if os.getenv('APP_ENVIRONMENT', 'production') == 'production' and os.getenv('NOK_DEPLOYMENT_ID'):
        control.require_backend(storage)
    route = control.route_key(family)
    before = storage.json_row_versions([route])
    pointer = storage.read_json(route, None)
    if pointer is None:
        return None
    if pointer['family'] != family or pointer['deployment_id'] != control.installation():
        raise ValueError('Selected account belongs to another installation')
    # Verify configured trust even on a hit, so certificate replacement fails closed.
    control._certificate()
    versions = storage.json_row_versions([route, restart._key(pointer['period_id'])])
    if before.get(route) != versions.get(route):
        raise ValueError('Concurrent route change; retry with a fresh account view')
    return (control.installation(), os.getenv('APP_ENVIRONMENT', 'production'),
            os.getenv('NOK_APPROVAL_CERT_SHA256'), tuple(sorted(versions.items())))


def cached_account_view(family, *, storage=None):
    """Return an already verified current view, or None without loading history.

    For read-only decisions such as closed-exchange deferral only. Transactions
    must continue through fresh selection and locked validation.
    """
    cache = _SCOPE.get()
    if cache is None:return None
    from services import production_restart as control
    storage = storage or control.get_storage_service()
    key = (storage, family, 'view')
    entry = cache.get(key)
    if entry is None:return None
    version = _version(storage, family)
    now = datetime.now(timezone.utc).timestamp()
    if entry[0] == version and entry[3] <= now <= entry[4]:
        from services.restart_io_metrics import reuse
        reuse('hit', family)
        return deepcopy(entry[1])
    cache.pop(key, None)
    return None


def _store(cache, key, version, value):
    size = len(json.dumps(value, ensure_ascii=False, default=str).encode('utf-8'))
    deadline = _valuation_deadline(value)
    # Take the lower clock boundary only after all source validation.
    validated_at = datetime.now(timezone.utc).timestamp()
    if size <= MAX_BYTES and deadline is not None:
        cache.pop(key, None)
        if sum(e[2] for e in cache.values()) + size > MAX_BYTES:
            cache.clear()
        cache[key] = (version, deepcopy(value), size, validated_at, deadline)


def _small_projection_source(document, approval):
    """Do not eagerly copy an unrequested large account/strategy state.

    This is a conservative optional-work bound, not a financial validator.
    Large/unsupported graphs simply retain their original on-demand read path.
    """
    latest = next((event['payload'].get('state', {}) for event in reversed(document['events'])
                   if event['kind'] == 'STRATEGY_RUN'), {})
    pending = [document['account'], latest, approval['settings']]
    budget = MAX_BYTES // 2
    nodes = 50000
    seen = set()
    while pending:
        value = pending.pop(); kind = type(value)
        budget -= 64
        if budget < 0:return False
        if kind is str:
            budget -= 6 * len(value)
        elif kind in (dict, list, tuple):
            if id(value) in seen:return False
            seen.add(id(value))
            count = len(value) * (2 if kind is dict else 1)
            nodes -= count
            if nodes < 0:return False
            if kind is dict:
                pending.extend(value.keys());pending.extend(value.values())
            else:pending.extend(value)
        elif kind not in (int, float, bool) and value is not None:
            return False
    return budget >= 0


def prime_related_views(chosen, *, storage, project):
    """Fan out an already verified snapshot into bounded detached account views.

    Never keep the bundle or a trading selection. Every additional account must
    have its own current route and signed control, bound to the exact bundle row
    revision observed before the original read. Invalid unrelated routes are not
    cached; a later request still follows the original fully verified path.
    """
    context = _READ.get()
    cache = _SCOPE.get()
    if context is None or cache is None or context[0] is not storage:
        return
    from services import production_restart as control, simulation_restart as restart
    from services.economic_opening import digest
    from services.restart_io_metrics import reuse
    _, selected_family, source_version = context
    bundle = chosen['bundle']
    bundle_key = restart._key(bundle['period_id'])
    expected = dict(source_version[-1]).get(bundle_key)
    if expected is None:
        return
    pending = []
    pending_bytes = 0
    for family in restart.CAPITALS:
        if family == selected_family:
            continue
        try:
            version = _version(storage, family)
            if version is None or dict(version[-1]).get(bundle_key) != expected:
                continue
            pointer = storage.read_json(control.route_key(family), None)
            if not pointer or pointer.get('period_id') != bundle['period_id']:
                continue
            approval = control._check_record(bundle, family, running=False)
            if pointer.get('grant_sha256') != digest(bundle['production_controls'][family]['grant']):
                raise ValueError('Route authorization mismatch')
            if not _small_projection_source(bundle['accounts'][family], approval):
                continue
            value = project(family, dict(pointer=pointer, bundle=bundle, approval=approval))
            if _version(storage, family) != version:
                raise ValueError('Concurrent related account change')
            size = len(json.dumps(value, ensure_ascii=False, default=str).encode('utf-8'))
            if size + pending_bytes <= MAX_BYTES and _valuation_deadline(value) is not None:
                pending.append(((storage, family, 'view'), version, value))
                pending_bytes += size
        except (ValueError, KeyError, TypeError, AttributeError):
            # Do not make a valid account depend on an unrelated broken route.
            # No cache entry is installed for that account; its own read raises.
            reuse('prime_rejected', family)
    if _version(storage, selected_family) != source_version:
        raise ValueError('Concurrent account change; retry with a fresh account view')
    for key, version, value in pending:
        _store(cache, key, version, value)


def account_read(fn):
    @wraps(fn)
    def call(family, *, storage=None, chosen=None):
        cache = _SCOPE.get()
        if cache is None or chosen is not None:
            return fn(family, storage=storage, chosen=chosen)
        from services import production_restart as control
        storage = storage or control.get_storage_service()
        version = _version(storage, family)
        if version is None:
            return fn(family, storage=storage, chosen=chosen)
        key = (storage, family, fn.__name__)
        entry = cache.get(key)
        now = datetime.now(timezone.utc).timestamp()
        from services.restart_io_metrics import reuse
        if entry is not None and entry[0] == version and entry[3] <= now <= entry[4]:
            reuse('hit', family)
            return deepcopy(entry[1])
        reuse('invalidated' if entry is not None else 'miss', family)
        # Never retain obsolete revisions, including after failed validation.
        cache.pop(key, None)
        token = _READ.set((storage, family, version))
        try:
            value = fn(family, storage=storage, chosen=chosen)
        finally:
            _READ.reset(token)
        if _version(storage, family) != version:
            raise ValueError('Concurrent account change; retry with a fresh account view')
        _store(cache, key, version, value)
        return value
    return call
