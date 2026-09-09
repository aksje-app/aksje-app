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
    stat = _cgroup_memory_stat()
    for key in ("anon", "file", "shmem", "kernel", "slab", "sock"):
        value = stat.get(key)
        if value is not None:
            result[f"cgroup_{key}_mb"] = round(value / mb, 1)
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


def _cgroup_memory_stat() -> dict[str, int]:
    """Return selected cgroup v2 memory.stat counters in bytes.

    memory.current includes both anonymous process memory and charged file cache.
    Keeping these separate is important on Render because a report can finish
    with modest Python RSS while the cgroup remains close to its hard limit.
    """
    paths = ("/sys/fs/cgroup/memory.stat", "/sys/fs/cgroup/memory/memory.stat")
    for path in paths:
        try:
            rows: dict[str, int] = {}
            for line in open(path, "r", encoding="utf-8"):
                parts = line.split()
                if len(parts) >= 2:
                    try:
                        rows[parts[0]] = int(parts[1])
                    except ValueError:
                        pass
            if rows:
                return rows
        except OSError:
            continue
    return {}


def reclaim_cgroup_memory(reason: str = "", *, target_mb: float = 256.0) -> dict[str, Any]:
    """Best-effort cgroup v2 reclaim after a heavy report phase.

    Linux exposes memory.reclaim specifically for proactively reclaiming charged
    memory (notably file cache) from a cgroup. Managed hosts may make the file
    read-only; that is treated as a normal unsupported outcome. No durable app
    data or application cache file is deleted.
    """
    before = memory_snapshot()
    requested = max(0.0, float(target_mb or 0.0))
    result: dict[str, Any] = {
        "reason": str(reason or ""),
        "requested_mb": round(requested, 1),
        "supported": False,
        "reclaimed_requested": False,
        "error": "",
        "before": before,
    }
    path = "/sys/fs/cgroup/memory.reclaim"
    if requested > 0:
        try:
            with open(path, "w", encoding="utf-8") as handle:
                handle.write(f"{int(requested * 1024 * 1024)}\n")
            result["supported"] = True
            result["reclaimed_requested"] = True
        except OSError as exc:
            result["error"] = f"{type(exc).__name__}: {exc}"
    result["after"] = memory_snapshot()
    return result


def terminal_memory_cleanup(reason: str = "", *, reclaim_mb: float = 384.0) -> dict[str, Any]:
    """Two-pass allocator cleanup plus safe cgroup reclaim attempt."""
    first = release_process_memory(f"{reason}:pass1")
    reclaim = reclaim_cgroup_memory(reason, target_mb=reclaim_mb)
    second = release_process_memory(f"{reason}:pass2")
    return {
        "reason": str(reason or ""),
        "first": first,
        "cgroup_reclaim": reclaim,
        "second": second,
        "final": memory_snapshot(),
    }


class MemoryPressureError(RuntimeError):
    pass


def scheduler_memory_soft_limit_mb() -> float:
    raw = os.getenv("SCHEDULER_MEMORY_SOFT_LIMIT_MB", "1450") or "1450"
    try:
        return max(512.0, float(raw))
    except (TypeError, ValueError):
        return 1450.0


def memory_guard(
    reason: str = "", *, soft_limit_mb: float | None = None,
    raise_on_pressure: bool = True, ignore_reclaimable_file_cache: bool = False,
    hard_limit_fraction: float = 0.97,
) -> dict[str, Any]:
    """Evaluate memory pressure with an optional reclaimable-file-cache-aware mode.

    ``memory.current`` includes Linux page cache. For the final report export on
    Render that cache can exceed 1 GiB even when Python RSS/anonymous memory is
    healthy. Treating all file cache as non-reclaimable produced false controlled
    stops. The optional mode still fails closed if anonymous/non-reclaimable
    memory exceeds the soft limit or the cgroup is extremely close to its hard
    limit. Scheduler callers retain the historical total-cgroup behavior unless
    they explicitly opt in.
    """
    snap = memory_snapshot()
    limit = float(soft_limit_mb if soft_limit_mb is not None else scheduler_memory_soft_limit_mb())
    rss = float(snap.get("process_rss_mb") or 0.0)
    cgroup = float(snap.get("cgroup_memory_current_mb") or 0.0)
    cgroup_limit = float(snap.get("cgroup_memory_limit_mb") or 0.0)
    anon = float(snap.get("cgroup_anon_mb") or 0.0)
    shmem = float(snap.get("cgroup_shmem_mb") or 0.0)
    kernel = float(snap.get("cgroup_kernel_mb") or 0.0)
    file_cache = float(snap.get("cgroup_file_mb") or 0.0)

    total_observed = max(rss, cgroup)
    non_reclaimable = max(rss, anon + shmem + kernel)
    hard_limit_pressure = bool(
        cgroup_limit > 0 and cgroup >= max(0.0, cgroup_limit * float(hard_limit_fraction))
    )
    if ignore_reclaimable_file_cache:
        observed = non_reclaimable
        pressure = bool(observed >= limit or hard_limit_pressure)
        basis = "NON_RECLAIMABLE_PLUS_HARD_LIMIT"
    else:
        observed = total_observed
        pressure = bool(observed >= limit)
        basis = "TOTAL_CGROUP_OR_RSS"

    result = {
        "reason": str(reason or ""),
        "soft_limit_mb": limit,
        "observed_mb": round(observed, 1),
        "total_observed_mb": round(total_observed, 1),
        "effective_non_reclaimable_mb": round(non_reclaimable, 1),
        "reclaimable_file_cache_mb": round(file_cache, 1),
        "ignore_reclaimable_file_cache": bool(ignore_reclaimable_file_cache),
        "pressure_basis": basis,
        "hard_limit_fraction": float(hard_limit_fraction),
        "hard_limit_pressure": hard_limit_pressure,
        "pressure": pressure,
        **snap,
    }
    if result["pressure"] and raise_on_pressure:
        raise MemoryPressureError(
            f"Memory guard {reason}: {observed:.1f} MB >= {limit:.1f} MB "
            f"(basis={basis}, total={total_observed:.1f} MB)"
        )
    return result
