"""Two independent production-style cycles with persisted pending entry; no external I/O."""
from copy import deepcopy
from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path

import autonomous_portfolio as ap


def test_pending_entry_survives_restart_and_buys_next_session(monkeypatch):
    store = {}
    now = [datetime(2026, 10, 9, 14, 0, tzinfo=timezone.utc)]
    params = replace(ap.AutonomousParameters(), initial_cash=100000,
                     enable_learning_probe_buys=False, notify_trades=False,
                     notify_risk_events=False)
    portfolio = {'cash': 100000.0, 'positions': {}, 'status': 'ACTIVE',
                 'initial_cash': 100000.0, 'high_watermark': 100000.0}
    store[str(ap.PORTFOLIO_PATH)] = deepcopy(portfolio)

    def read(path, default):
        return deepcopy(store.get(str(path), default))

    def write(path, value):
        store[str(path)] = deepcopy(value)

    monkeypatch.setattr(ap, '_read', read)
    monkeypatch.setattr(ap, '_write', write)
    monkeypatch.setattr(ap, 'load_parameters', lambda: params)
    monkeypatch.setattr(ap, 'load_portfolio', lambda: read(ap.PORTFOLIO_PATH, portfolio))
    monkeypatch.setattr(ap, 'load_learning_portfolio', lambda: {'positions': {}, 'cash': 0})
    monkeypatch.setattr(ap, '_clock', lambda tz=None: now[0])
    monkeypatch.setattr(ap, '_now', lambda: now[0].isoformat())
    for name in ('_append_audit', '_record_trade', '_record_decisions',
                 '_record_learning_decisions', '_append_equity_history',
                 '_append_learning_equity_history', '_notification'):
        monkeypatch.setattr(ap, name, lambda *a, **kw: None)
    monkeypatch.setattr(ap, '_update_learning_positions', lambda *a: ([], []))
    monkeypatch.setattr(ap, 'get_market_snapshot_service',
                        lambda: (_ for _ in ()).throw(RuntimeError('isolated fixture')))

    candidate = dict(ticker='MSFT', investment_score=90, risk_score=10,
                     data_quality_score=100, price=99, sector='Technology',
                     portfolio_action='BUY', autonomy_outcome_code='KJØPSKANDIDAT',
                     valid_for_decision=True, evidence_valid_for_decision=True,
                     final_decision_ready=True, session_date='2026-10-09',
                     session_open=99, previous_close=98)

    first = ap.run_autonomous_cycle([candidate], 'ENTRY-DAY-1')
    assert not [x for x in first['portfolio_trades'] if x['action'] == 'BUY']
    pending = read(ap.PENDING_ENTRIES_PATH, {})
    assert pending['MSFT']['entry_signal_date'] == '2026-10-09'
    assert pending['MSFT']['signal_run_id'] == 'ENTRY-DAY-1'

    # New call re-reads the persisted store; its candidate has no signal timestamp.
    now[0] = datetime(2026, 10, 12, 14, 0, tzinfo=timezone.utc)
    second = dict(candidate, session_date='2026-10-12', session_open=100,
                  previous_close=99, price=101)
    second['execution_quote']={'price':101,'market_data_at':now[0].isoformat(),'source':'yfinance 5m Close','adjustment':'raw'}
    result = ap.run_autonomous_cycle([second], 'ENTRY-DAY-2')
    buys = [x for x in result['portfolio_trades'] if x['action'] == 'BUY']
    assert len(buys) == 1
    assert buys[0]['price'] == 101  # observed fill, not the hours-old session open
    assert buys[0]['entry_signal_date'] == '2026-10-09'
    assert buys[0]['entry_signal_run_id'] == 'ENTRY-DAY-1'
    assert 'MSFT' not in read(ap.PENDING_ENTRIES_PATH, {})
