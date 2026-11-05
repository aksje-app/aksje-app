"""Payload-free counters for every complete restart-bundle JSON decode."""
from collections import Counter
from threading import Lock
import logging
import traceback

_LOCK = Lock()
_COUNTS = Counter()
_BYTES = Counter()
_CALLERS = Counter()
_REUSE = Counter()


def reset():
    with _LOCK:
        _COUNTS.clear()
        _BYTES.clear()
        _CALLERS.clear()
        _REUSE.clear()


def reuse(kind, family):
    with _LOCK:
        _REUSE[(family, kind)] += 1


def record(name, kind, payload_bytes=None, *, raw=None):
    if not (name.startswith('simulation_restarts/') and name.endswith('/bundle.json')):
        return
    if payload_bytes is None:
        # Bound temporary UTF-8 allocations; a second 100 MiB encoding would
        # otherwise distort the very peak this instrumentation is measuring.
        payload_bytes = sum(len(raw[i:i+65536].encode('utf-8')) for i in range(0, len(raw), 65536))
    frames = traceback.extract_stack(limit=14)[:-1]
    caller = ' > '.join(f.filename.rsplit('/', 1)[-1] + ':' + f.name + ':' + str(f.lineno)
                        for f in frames if f.filename.rsplit('/', 1)[-1] not in {'storage_service.py', 'restart_io_metrics.py'})
    with _LOCK:
        _COUNTS[(name, kind)] += 1
        _BYTES[(name, kind)] += payload_bytes
        _CALLERS[(kind, caller if len(_CALLERS) < 128 or (kind, caller) in _CALLERS else 'OTHER')] += 1
    logging.warning('RESTART_JSON_LOAD key=%s kind=%s bytes=%s caller=%s', name, kind, payload_bytes, caller)


def snapshot():
    with _LOCK:
        return {'total_full_loads': sum(_COUNTS.values()),
                'account_reuse': [{'family': family, 'kind': kind, 'count': count}
                                  for (family, kind), count in sorted(_REUSE.items())],
                'documents': [{'key': key, 'kind': kind, 'loads': count, 'bytes': _BYTES[(key, kind)]}
                              for (key, kind), count in sorted(_COUNTS.items())],
                'callers': [{'kind': kind, 'caller': caller, 'loads': count}
                            for (kind, caller), count in sorted(_CALLERS.items())]}
