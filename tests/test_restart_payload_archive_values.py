import copy
import json

import pytest

from services.restart_payload_archive_values import FrozenDict, FrozenList, LazyPayload, PayloadCache


def proxy(payload=None):
    calls = []
    value = {'nested': {'a': [1, {'x': 2}]}, 'z': 3} if payload is None else payload
    def load(ref):
        calls.append(ref['key'])
        return value
    cache = PayloadCache(load)
    return LazyPayload({'key': 'one'}, cache), calls


def test_lazy_mapping_and_all_serializers_observe_real_payload():
    p, calls = proxy()
    assert calls == []
    expected = {'nested': {'a': [1, {'x': 2}]}, 'z': 3}
    assert bool(p)
    assert len(p) == 2
    assert list(p) == ['nested', 'z']
    assert set(p.keys()) == set(expected)
    assert list(p.values()) == list(expected.values())
    assert list(p.items()) == list(expected.items())
    assert 'nested' in p and 'missing' not in p
    assert p.get('z') == 3 and p.get('missing', 9) == 9
    assert dict(p) == expected and {**p} == expected
    assert p == expected and expected == p
    assert not (p != expected) and not (expected != p)
    assert p != {} and p.copy() == expected
    assert json.loads(json.dumps(p)) == expected
    assert json.dumps(p, sort_keys=True) == json.dumps(expected, sort_keys=True)
    assert json.loads(''.join(json.JSONEncoder(sort_keys=True).iterencode(p))) == expected
    assert repr(p).startswith('LazyPayload(reference=')
    with pytest.raises(KeyError):
        p['missing']
    assert calls == ['one']


def test_empty_payload_serializes_and_compares_as_empty():
    p, calls = proxy({})
    assert not p and len(p) == 0
    assert dict(p) == {} and {**p} == {} and p == {}
    assert json.dumps(p) == '{}'
    assert ''.join(json.JSONEncoder().iterencode(p)) == '{}'
    assert calls == ['one']


def test_single_decoded_entry_is_shared_per_cache_and_evicted():
    calls = []
    def load(ref):
        calls.append(ref['key'])
        return {'key': ref['key']}
    cache = PayloadCache(load)
    a, b = LazyPayload({'key': 'a'}, cache), LazyPayload({'key': 'b'}, cache)
    same_a = LazyPayload({'key': 'a'}, cache)
    assert a['key'] == same_a['key'] == 'a'
    assert calls == ['a']
    assert b['key'] == 'b'
    assert a['key'] == 'a'
    assert calls == ['a', 'b', 'a']
    other = LazyPayload({'key': 'a'}, PayloadCache(load))
    assert other['key'] == 'a'
    assert calls == ['a', 'b', 'a', 'a']


@pytest.mark.parametrize('method,args', [('__setitem__', ('z', 4)), ('__delitem__', ('z',)), ('clear', ()), ('pop', ('z',)), ('popitem', ()), ('setdefault', ('z', 4)), ('update', ({'z': 4},)), ('__ior__', ({'z': 4},))])
def test_lazy_and_frozen_dict_mutation_always_raises(method, args):
    p, _ = proxy()
    for value in (p, p['nested'], p.reference):
        with pytest.raises(TypeError):
            getattr(value, method)(*args)


@pytest.mark.parametrize('method,args', [('__setitem__', (0, 2)), ('__delitem__', (0,)), ('append', (3,)), ('extend', ([3],)), ('insert', (0, 3)), ('pop', ()), ('remove', (1,)), ('clear', ()), ('sort', ()), ('reverse', ()), ('__iadd__', ([3],)), ('__imul__', (2,))])
def test_frozen_list_rejects_all_mutations(method, args):
    p, _ = proxy()
    with pytest.raises(TypeError):
        getattr(p['nested']['a'], method)(*args)


def test_explicit_state_deepcopy_is_mutable_and_does_not_change_history():
    p, _ = proxy()
    for original in (p['nested'],):
        result = copy.deepcopy(original)
        assert type(result) is dict
        target = result
        assert type(target['a']) is list
        target['a'][1]['x'] = 99
        target['a'].append('new')
        assert p['nested']['a'][1]['x'] == 2
    result = copy.deepcopy(p['nested']['a'])
    assert type(result) is list
    result[1]['x'] = 99
    assert p['nested']['a'][1]['x'] == 2
    shallow = p.copy()
    shallow['z'] = 10
    assert p['z'] == 3


def test_freezing_does_not_freeze_or_mutate_loader_input():
    source = {'a': [{'b': 1}]}
    p, _ = proxy(source)
    assert isinstance(p['a'], FrozenList)
    assert isinstance(p['a'][0], FrozenDict)
    source['a'][0]['b'] = 99
    assert p['a'][0]['b'] == 1


def test_descriptor_is_copied_and_loader_must_return_dict():
    ref = {'key': 'a', 'nested': {'value': 1}}
    p = LazyPayload(ref, PayloadCache(lambda r: []))
    ref['key'] = 'different'
    assert p.reference['key'] == 'a'
    with pytest.raises(TypeError, match='dict'):
        p.get('anything')


def test_loader_errors_do_not_install_cache_entry():
    calls = []
    def load(ref):
        calls.append(1)
        if len(calls) == 1:
            raise ValueError('checksum')
        return {'ok': True}
    p = LazyPayload({'key': 'a'}, PayloadCache(load))
    with pytest.raises(ValueError, match='checksum'):
        p['ok']
    assert p['ok'] is True
    assert len(calls) == 2


def test_remaining_mapping_reads_use_payload_not_placeholder():
    p, _ = proxy({'a': 1, 'b': 2})
    assert list(reversed(p)) == ['b', 'a']
    assert p | {'c': 3} == {'a': 1, 'b': 2, 'c': 3}
    assert {'c': 3} | p == {'a': 1, 'b': 2, 'c': 3}
    target = {}
    target.update(p)
    assert target == {'a': 1, 'b': 2}
    assert copy.copy(p) == target
    assert str(p) == repr(p)
    assert p.fromkeys(['x'], 1) == {'x': 1}
    assert FrozenDict(target) == p
    assert not (FrozenDict(target) != p)


def test_payload_objects_cannot_be_reinitialized_to_mutate_history():
    p, _ = proxy()
    with pytest.raises(TypeError):
        p.__init__({'key': 'other'}, p._cache)
    with pytest.raises(TypeError):
        p['nested'].__init__({'changed': True})
    with pytest.raises(TypeError):
        p['nested']['a'].__init__([99])


def test_whole_root_deepcopy_preserves_lazy_payloads_without_loading_history():
    calls = []
    def loader(reference):
        calls.append(reference['key'])
        return {'state': {'positions': [{'ticker': 'AAA'}]}}
    cache = PayloadCache(loader)
    payload = LazyPayload({'key': 'one', 'sha256': 'a' * 64, 'uncompressed_bytes': 45}, cache)
    root = {'accounts': {'paper': {'events': [{'payload': payload}, {'payload': payload}]}}, 'live': {'cash': 100}}
    copied = copy.deepcopy(root)
    assert calls == []
    cloned = copied['accounts']['paper']['events'][0]['payload']
    assert isinstance(cloned, LazyPayload)
    assert cloned is copied['accounts']['paper']['events'][1]['payload']
    assert cloned.reference is payload.reference
    assert cloned._cache is cache
    copied['live']['cash'] = 50
    assert root['live']['cash'] == 100
    restored = copy.deepcopy(cloned['state'])
    assert calls == ['one']
    restored['positions'][0]['ticker'] = 'BBB'
    assert cloned['state']['positions'][0]['ticker'] == 'AAA'


def test_proxy_equality_uses_validated_descriptors_without_loading_payloads():
    def forbidden(reference):
        raise AssertionError('comparison must not load history')
    ref = {'key': 'one', 'sha256': 'a' * 64, 'uncompressed_bytes': 45}
    a = LazyPayload(ref, PayloadCache(forbidden))
    same = LazyPayload(dict(ref), PayloadCache(forbidden))
    assert a == same
    assert not (a != same)
    for field, value in [('key', 'other'), ('sha256', 'b' * 64), ('uncompressed_bytes', 46)]:
        different = LazyPayload({**ref, field: value}, PayloadCache(forbidden))
        assert a != different
        assert not (a == different)


def test_whole_root_repr_uses_bounded_descriptor_without_loading_payloads():
    def forbidden(reference):
        raise AssertionError('repr must not load history')
    payload = LazyPayload({'key': 'one', 'sha256': 'a' * 64, 'uncompressed_bytes': 45}, PayloadCache(forbidden))
    root = {'events': [{'payload': payload}]}
    rendered = repr(root)
    assert 'LazyPayload(reference=' in rendered
    assert 'one' in rendered
    assert len(repr(payload)) < 600
