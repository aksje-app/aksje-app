import controlled_parameter_learning as learning


def test_distinct_legacy_exits_without_trade_ids_are_not_discarded(monkeypatch):
    rows = [
        {'action': 'SELL', 'ticker': 'AAA', 'timestamp': '2026-10-01', 'price': 110, 'pnl': 10},
        {'action': 'SELL', 'ticker': 'BBB', 'timestamp': '2026-10-02', 'price': 90, 'pnl': -10},
    ]
    monkeypatch.setattr(learning, 'load_learning_trades', lambda: rows + [dict(rows[0])])
    assert len(learning._closed_learning_trades()) == 2


def test_same_trade_id_remains_deduplicated(monkeypatch):
    row = {'action': 'SELL', 'trade_id': 'T1', 'ticker': 'AAA', 'pnl': 10}
    monkeypatch.setattr(learning, 'load_learning_trades', lambda: [row, dict(row)])
    assert len(learning._closed_learning_trades()) == 1
