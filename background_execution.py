"""Thread-local execution context for non-UI background workers.

Background report workers must never read or mutate Streamlit session state.
The context is deliberately thread-local so the normal Streamlit script thread
continues to use UI state while worker threads use durable storage only.
"""
from __future__ import annotations

from contextlib import contextmanager
import threading
from typing import Iterator

_LOCAL = threading.local()


def is_background_execution() -> bool:
    return bool(getattr(_LOCAL, "active", False))


def background_execution_id() -> str:
    return str(getattr(_LOCAL, "execution_id", "") or "")


@contextmanager
def background_execution(execution_id: str = "") -> Iterator[None]:
    previous_active = bool(getattr(_LOCAL, "active", False))
    previous_execution_id = str(getattr(_LOCAL, "execution_id", "") or "")
    _LOCAL.active = True
    _LOCAL.execution_id = str(execution_id or "")
    try:
        yield
    finally:
        _LOCAL.active = previous_active
        _LOCAL.execution_id = previous_execution_id
