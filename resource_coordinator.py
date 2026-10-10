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


def optional_capacity():
    from autonomous_portfolio import _available_memory_mb
    headroom = _available_memory_mb()
    load = os.getloadavg()[0] / max(1, os.cpu_count() or 1)
    return {'ready': (headroom is None or headroom >= 384) and load < 1.5,
            'headroom_mb': headroom, 'load_per_cpu': round(load, 2)}


def verify_lane():
    """Fail before publication if the DB session lost its execution ownership."""
    conn=_connection.get()
    if conn is not None:
        with conn.cursor() as cursor:
            cursor.execute('SELECT EXISTS (SELECT 1 FROM pg_locks WHERE locktype=\'advisory\' AND pid=pg_backend_pid() AND objid=%s)',(LOCK_ID,))
            if not cursor.fetchone()[0]:raise RuntimeError('Felles kjørelås er tapt; publisering blokkert')
