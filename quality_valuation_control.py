"""One manual quality screen across web processes; never takes report lock."""
from __future__ import annotations

from contextlib import contextmanager
import os
import threading
from typing import Iterator


_LOCAL = threading.Lock()
_LOCK_ID = 1871606


@contextmanager
def single_manual_screen() -> Iterator[bool]:
    database_url = os.getenv("DATABASE_URL", "").strip()
    connection = None
    acquired = False
    try:
        if database_url:
            import psycopg2
            connection = psycopg2.connect(database_url, connect_timeout=4)
            connection.autocommit = True
            with connection.cursor() as cursor:
                cursor.execute("SELECT pg_try_advisory_lock(%s)", (_LOCK_ID,))
                acquired = bool(cursor.fetchone()[0])
        else:
            acquired = _LOCAL.acquire(blocking=False)
        yield acquired
    finally:
        if connection is not None:
            try:
                if acquired:
                    with connection.cursor() as cursor:
                        cursor.execute("SELECT pg_advisory_unlock(%s)", (_LOCK_ID,))
            finally:
                connection.close()
        elif acquired:
            _LOCAL.release()
