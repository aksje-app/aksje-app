"""Read-only historical payload values with a bounded, root-owned decode cache.

Descriptors and blobs are authenticated by the archive loader. This module only
controls materialization and ordinary Python container mutation. Deliberately
calling base-class mutation methods bypasses Python subclass guards and is not
part of the supported historical payload API.
"""
from __future__ import annotations

from collections.abc import Callable, Mapping
import copy
import json
import threading
from typing import Any


def _immutable(*args, **kwargs):
    raise TypeError('Historical archived payloads are immutable; deepcopy before changing them')


def _freeze(value):
    if isinstance(value, Mapping):
        return FrozenDict(value)
    if isinstance(value, (list, tuple)):
        return FrozenList(value)
    return value


class FrozenDict(dict):
    """Recursively immutable dict compatible with standard JSON serialization."""
    __slots__ = ('_sealed',)

    def __init__(self, value=(), **kwargs):
        if hasattr(self, '_sealed'):
            _immutable()
        source = dict(value, **kwargs)
        dict.__init__(self, ((key, _freeze(item)) for key, item in source.items()))
        self._sealed = True

    def __eq__(self, other):
        return dict.__eq__(self, other._payload() if isinstance(other, LazyPayload) else other)

    def __ne__(self, other):
        result = self.__eq__(other)
        return NotImplemented if result is NotImplemented else not result

    __setitem__ = __delitem__ = clear = pop = popitem = setdefault = update = __ior__ = _immutable

    def __copy__(self):
        return dict(self)

    def __deepcopy__(self, memo):
        result = {}
        memo[id(self)] = result
        result.update((copy.deepcopy(key, memo), copy.deepcopy(item, memo)) for key, item in self.items())
        return result


class FrozenList(list):
    """Recursively immutable list; deepcopy explicitly restores mutable lists."""
    __slots__ = ('_sealed',)

    def __init__(self, values=()):
        if hasattr(self, '_sealed'):
            _immutable()
        list.__init__(self, (_freeze(item) for item in values))
        self._sealed = True

    __setitem__ = __delitem__ = append = extend = insert = pop = remove = clear = sort = reverse = __iadd__ = __imul__ = _immutable

    def __copy__(self):
        return list(self)

    def __deepcopy__(self, memo):
        result = []
        memo[id(self)] = result
        result.extend(copy.deepcopy(item, memo) for item in self)
        return result


class PayloadCache:
    """One decoded entry shared by lazy payloads in a single hydrated root.

    A loader may separately keep a bounded encoded-byte LRU. LazyPayload never
    retains a decoded value itself, so traversing historical events cannot grow
    the decoded cache with the journal's length. No process-global cache exists.
    """
    def __init__(self, loader: Callable[[Mapping[str, Any]], dict]):
        self._loader = loader
        self._key = None
        self._value = None
        self._lock = threading.RLock()

    def get(self, reference: Mapping[str, Any]) -> FrozenDict:
        key = json.dumps(reference, sort_keys=True, separators=(',', ':'))
        with self._lock:
            if key == self._key and self._value is not None:
                return self._value
            loaded = self._loader(reference)
            if not isinstance(loaded, dict):
                raise TypeError('Archived payload loader must return a dict')
            value = FrozenDict(loaded)
            self._key, self._value = key, value
            return value


class LazyPayload(dict):
    """A read-only dict proxy whose entire payload is fetched only on access."""
    __slots__ = ('_reference', '_cache')

    def __init__(self, reference: Mapping[str, Any], cache: PayloadCache):
        if hasattr(self, '_reference'):
            _immutable()
        # CPython's JSON encoder checks underlying dict size before invoking
        # subclass items(). A nonempty placeholder prevents its empty fastpath.
        # All supported reads delegate to the real immutable payload below.
        dict.__init__(self, {'__archived_payload_placeholder__': None})
        self._reference = FrozenDict(reference)
        self._cache = cache

    @property
    def reference(self) -> FrozenDict:
        return self._reference

    def _payload(self) -> FrozenDict:
        return self._cache.get(self._reference)

    def __getitem__(self, key):
        return self._payload()[key]

    def __iter__(self):
        return iter(self._payload())

    def __reversed__(self):
        return reversed(self._payload())

    @classmethod
    def fromkeys(cls, iterable, value=None):
        return dict.fromkeys(iterable, value)

    def __len__(self):
        return len(self._payload())

    def __contains__(self, key):
        return key in self._payload()

    def get(self, key, default=None):
        return self._payload().get(key, default)

    def keys(self):
        return self._payload().keys()

    def values(self):
        return self._payload().values()

    def items(self):
        return self._payload().items()

    def __repr__(self):
        return 'LazyPayload(reference=' + repr(self._reference)[:512] + ')'

    def __eq__(self, other):
        if isinstance(other, LazyPayload):
            # Validated descriptors bind the content digest, raw size and
            # period-scoped blob key. Root comparisons must not hydrate history.
            return self._reference == other._reference
        return self._payload() == other

    def __ne__(self, other):
        return not self == other

    def copy(self):
        return dict(self._payload())

    def __copy__(self):
        return self.copy()

    def __deepcopy__(self, memo):
        # Root/account copies preserve immutable historical proxies. Explicit
        # deepcopy(payload['state']) still restores mutable dict/list state.
        result = dict.__new__(type(self))
        dict.__init__(result, {'__archived_payload_placeholder__': None})
        result._reference, result._cache = self._reference, self._cache
        memo[id(self)] = result
        return result

    def __or__(self, other):
        return self.copy() | other

    def __ror__(self, other):
        return other | self.copy()

    __setitem__ = __delitem__ = clear = pop = popitem = setdefault = update = __ior__ = _immutable
