"""Cross-process execution lane. PostgreSQL session locks release on disconnect.

This lane covers the cron cycle and independent manual workers. Nested calls in
one thread reuse the lane; a child process must never inherit that ownership.
"""
from contextlib import contextmanager
from contextvars import ContextVar
from datetime import datetime, timezone
from functools import wraps
import fcntl
import os
import threading
import math
from pathlib import Path

from storage_architecture import runtime_data_path

LOCK_ID = 19343501
_owner = ContextVar('heavy_work_owner', default=None)
_connection = ContextVar('heavy_work_connection',default=None)
_local = threading.Lock()


@contextmanager
def execution_lane(name):
    inherited = _owner.get()
    if inherited and inherited == (os.getpid(), threading.get_ident()):
        yield True
        return
    conn = handle = token = connection_token = None
    acquired = False
    local_acquired = False
    try:
        if os.getenv('DATABASE_URL', '').strip():
            import psycopg2
            conn = psycopg2.connect(os.environ['DATABASE_URL'], connect_timeout=5)
            conn.autocommit = True
            with conn.cursor() as cur:
                cur.execute('SELECT pg_try_advisory_lock(%s)', (LOCK_ID,))
                acquired = bool(cur.fetchone()[0])
        else:
            local_acquired = _local.acquire(blocking=False)
            if local_acquired:
                path = runtime_data_path('coordinator', 'execution.lock')
                path.parent.mkdir(parents=True, exist_ok=True)
                handle = path.open('a')
                try:
                    fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
                    acquired = True
                except BlockingIOError:
                    pass
        if acquired:
            token = _owner.set((os.getpid(), threading.get_ident()))
            connection_token = _connection.set(conn)
        yield acquired
    finally:
        if token is not None:
            _owner.reset(token)
        if connection_token is not None:
            _connection.reset(connection_token)
        if conn is not None:
            # Closing the session releases the lock even after an exception.
            conn.close()
        if handle is not None:
            handle.close()
        if local_acquired:
            _local.release()


def coordinated(name, deferred=None):
    def decorate(fn):
        @wraps(fn)
        def call(*args, **kwargs):
            with execution_lane(name) as acquired:
                if not acquired:
                    return deferred(*args, **kwargs) if deferred else {
                        'state': 'DEFERRED_BUSY', 'component': name,
                        'completed_at': datetime.now(timezone.utc).isoformat(),
                        'message': 'En annen tung jobb kjører; prøves igjen i neste syklus.',
                    }
                return fn(*args, **kwargs)
        return call
    return decorate


def _container_cpu_pressure(root=Path('/sys/fs/cgroup')):
    """Only use PSI from a quota-limited cgroup, never host load as a veto."""
    try:
        quota, period = (root/'cpu.max').read_text().split()
        if quota == 'max' or int(quota) <= 0 or int(period) <= 0:
            return None
        for line in (root/'cpu.pressure').read_text().splitlines():
            if line.startswith('some '):
                value = float(dict(field.split('=') for field in line.split()[1:])['avg10'])
                return value if math.isfinite(value) and 0 <= value <= 100 else None
    except (OSError, ValueError, KeyError):
        pass
    return None


def optional_capacity():
    from autonomous_portfolio import _available_memory_mb
    headroom = _available_memory_mb()
    try: load = round(os.getloadavg()[0] / max(1, os.cpu_count() or 1), 2)
    except (OSError, AttributeError): load = None
    pressure = _container_cpu_pressure()
    reasons = []
    if headroom is not None and headroom < 384: reasons.append('MEMORY_HEADROOM')
    if pressure is not None and pressure >= 50: reasons.append('CONTAINER_CPU_PRESSURE')
    return {'ready': not reasons, 'reasons': reasons, 'headroom_mb': headroom,
            'minimum_headroom_mb': 384, 'host_load_per_cpu': load,
            'host_load_policy': 'DIAGNOSTIC_ONLY', 'cpu_pressure_avg10_pct': pressure,
            'cpu_pressure_limit_pct': 50, 'cpu_source': 'CGROUP_PSI' if pressure is not None else 'UNAVAILABLE'}


def verify_lane():
    """Fail before publication if the DB session lost its execution ownership."""
    conn=_connection.get()
    if conn is not None:
        with conn.cursor() as cursor:
            cursor.execute('SELECT EXISTS (SELECT 1 FROM pg_locks WHERE locktype=\'advisory\' AND pid=pg_backend_pid() AND objid=%s)',(LOCK_ID,))
            if not cursor.fetchone()[0]:raise RuntimeError('Felles kjørelås er tapt; publisering blokkert')
