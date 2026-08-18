"""Bounded process-memory observability and safe phase cleanup.

The production web worker executes more than one report during its lifetime.
CPython can therefore retain freed arenas after pandas/yfinance work even when
the corresponding Python objects are no longer reachable.  This module keeps
cleanup explicit and observable without deleting durable caches or user data.
"""
from __future__ import annotations

import ctypes
import gc
import os
import resource
from typing import Any


def _read_int(path: str) -> int | None:
    try:
        raw = open(path, "r", encoding="utf-8").read().strip()
        if not raw or raw == "max":
            return None
        return int(raw)
    except (OSError, TypeError, ValueError):
        return None


def _current_rss_bytes() -> int | None:
    try:
        for line in open("/proc/self/status", "r", encoding="utf-8"):
            if line.startswith("VmRSS:"):
                return int(line.split()[1]) * 1024
    except (OSError, TypeError, ValueError, IndexError):
        return None
    return None


def _cgroup_memory() -> tuple[int | None, int | None]:
    # Render uses cgroup v2.  Keep v1 support for local/container validation.
    current = _read_int("/sys/fs/cgroup/memory.current")
    limit = _read_int("/sys/fs/cgroup/memory.max")
    if current is None:
        current = _read_int("/sys/fs/cgroup/memory/memory.usage_in_bytes")
    if limit is None:
        limit = _read_int("/sys/fs/cgroup/memory/memory.limit_in_bytes")
    if limit is not None and limit >= (1 << 60):
        limit = None
    return current, limit


def memory_snapshot() -> dict[str, Any]:
    rss = _current_rss_bytes()
    current, limit = _cgroup_memory()
    try:
        peak = int(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss)
        peak_bytes = peak * 1024 if peak < 10_000_000 else peak
    except Exception:
        peak_bytes = None
    mb = 1024.0 * 1024.0
    result: dict[str, Any] = {"process_pid": os.getpid()}
    if rss is not None:
        result["process_rss_mb"] = round(rss / mb, 1)
    if peak_bytes is not None:
        result["process_peak_rss_mb"] = round(peak_bytes / mb, 1)
    if current is not None:
        result["cgroup_memory_current_mb"] = round(current / mb, 1)
    if limit is not None:
        result["cgroup_memory_limit_mb"] = round(limit / mb, 1)
        if current is not None:
            result["cgroup_memory_headroom_mb"] = round(max(0, limit - current) / mb, 1)
            result["cgroup_memory_used_pct"] = round(100.0 * current / max(1, limit), 1)
    return result


def release_process_memory(reason: str = "") -> dict[str, Any]:
    """Collect unreachable objects and return free libc arenas on Linux."""
    before = memory_snapshot()
    collected = gc.collect()
    trimmed = False
    try:
        libc = ctypes.CDLL(None)
        malloc_trim = getattr(libc, "malloc_trim")
        malloc_trim.argtypes = [ctypes.c_size_t]
        malloc_trim.restype = ctypes.c_int
        trimmed = bool(malloc_trim(0))
    except (AttributeError, OSError):
        pass
    after = memory_snapshot()
    return {
        "reason": str(reason or ""), "objects_collected": int(collected),
        "allocator_trimmed": trimmed, "before": before, "after": after,
    }
