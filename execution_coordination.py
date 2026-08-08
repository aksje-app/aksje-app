"""Cross-process lease for report execution, shared by UI and cron workers."""
from __future__ import annotations

import os
import threading
from contextlib import contextmanager

_LOCAL_LOCK = threading.Lock()
_REPORT_EXECUTION_LOCK_ID = 1871502


@contextmanager
def report_execution_lock():
    connection = None
    acquired = False
    database_url = str(os.getenv("DATABASE_URL") or "").strip()
    try:
        if database_url:
            import psycopg2

            connection = psycopg2.connect(database_url, connect_timeout=5)
            cursor = connection.cursor()
            cursor.execute("SELECT pg_try_advisory_lock(%s)", (_REPORT_EXECUTION_LOCK_ID,))
            acquired = bool(cursor.fetchone()[0])
        else:
            acquired = _LOCAL_LOCK.acquire(blocking=False)
        yield acquired
    finally:
        if connection is not None:
            try:
                if acquired:
                    cursor = connection.cursor()
                    cursor.execute("SELECT pg_advisory_unlock(%s)", (_REPORT_EXECUTION_LOCK_ID,))
                connection.close()
            except Exception:
                pass
        elif acquired:
            _LOCAL_LOCK.release()
