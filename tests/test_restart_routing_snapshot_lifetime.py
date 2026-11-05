"""An ordinary route must release its read snapshot before locked execution."""
import weakref
from services import production_routing as routing, restart_trading as trading


class Bundle(dict):
    pass


def selection_factory(family, refs):
    def selected(*args, **kwargs):
        bundle = Bundle(accounts={})
        refs.append(weakref.ref(bundle))
        return {'pointer': {'family': family}, 'approval': {'settings': {}}, 'bundle': bundle}
    return selected


def test_paper_does_not_retain_previous_bundle_while_transaction_loads(monkeypatch):
    refs = []
    monkeypatch.setattr(routing.control, 'selected', selection_factory('paper', refs))
    monkeypatch.setattr(routing, 'completed', lambda *args: None)
    monkeypatch.setattr(routing, 'context', lambda *args, **kw: {'evidence_blocks': []})
    monkeypatch.setattr(routing, 'strategy_settings', lambda *args, **kw: {})
    def execute(**kwargs):
        assert refs[0]() is None, 'pre-execution bundle still occupies memory'
        return {'outcomes': [{'ok': True, 'message': 'accepted'}]}
    monkeypatch.setattr(trading, 'paper', execute)
    assert routing.paper('TEST', 'BUY') == (True, 'accepted')


def test_super_stop_does_not_retain_previous_bundle_during_transaction(monkeypatch):
    refs = []
    monkeypatch.setattr(routing.control, 'selected', selection_factory('super_portfolio', refs))
    monkeypatch.setattr(routing, 'completed', lambda *args: None)
    monkeypatch.setattr(routing, 'context', lambda *args, **kw: {'evidence_blocks': []})
    monkeypatch.setattr(routing, 'strategy_settings', lambda *args, **kw: {})
    def execute(**kwargs):
        assert refs[0]() is None, 'stop-surveillance snapshot overlaps locked bundle'
        return {'changes': []}
    monkeypatch.setattr(trading, 'run', execute)
    assert routing.super_risk() == {'changes': []}
