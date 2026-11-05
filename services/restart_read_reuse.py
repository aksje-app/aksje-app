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
        value = fn(family, storage=storage, chosen=chosen)
        if _version(storage, family) != version:
            raise ValueError('Concurrent account change; retry with a fresh account view')
        size = len(json.dumps(value, ensure_ascii=False, default=str).encode('utf-8'))
        deadline = _valuation_deadline(value)
        if size <= MAX_BYTES and deadline is not None:
            if sum(e[2] for e in cache.values()) + size > MAX_BYTES:
                cache.clear()
            cache[key] = (version, deepcopy(value), size, now, deadline)
        return value
    return call
