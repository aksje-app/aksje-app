from services import production_routing as routing


def test_projection_uses_supplied_verified_selection_without_lookup(monkeypatch):
    from services import portfolio_accounting as ledger
    chosen = {'pointer': {'family': 'autonomy'}, 'approval': {'period_id': 'p', 'settings': {}},
              'bundle': {'production_controls': {'autonomy': {'status': 'RUNNING'}},
                         'accounts': {'autonomy': {'account': {'positions': {}, 'trades': [], 'cash': 5,
                                                              'initial_cash': 5, 'realized_pnl': 0}, 'events': []}}}}
    def unexpected(*args, **kw):
        raise AssertionError('duplicate restart bundle read')
    monkeypatch.setattr(routing.control, 'selected', unexpected)
    monkeypatch.setattr(ledger, 'report', lambda *a, **kw: {'new_period': {'verification': {
        'verified_nav': 5, 'verified_net_return_pct': 0}}})
    assert routing.view('autonomy', chosen=chosen)['portfolio_value'] == 5
