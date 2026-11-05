"""Closed exchange deferral cannot create quotes, sales or weaken open checks."""
from datetime import datetime, timezone
from copy import deepcopy
import pytest
from services import production_routing as routing


def at(value):return datetime.fromisoformat(value).replace(tzinfo=timezone.utc)


@pytest.mark.parametrize('when', ['2026-11-05T23:00:00','2026-11-07T12:00:00',
                                  '2026-12-25T12:00:00','2026-10-25T12:00:00'])
def test_closed_stock_exchange_has_explicit_defer_and_next_open(when):
    result=routing._closed_held_exchanges({'EVO.ST':{}},at(when))
    assert result['state']=='NOT_DUE' and result['reason']=='MARKET_CLOSED'
    assert result['changes']==[] and result['deferred'] is True
    assert result['next_market_open']['SVERIGE']['utc']>at(when).isoformat()


@pytest.mark.parametrize('positions', [{}, {'EVO.ST':{},'AAPL':{}}, {'BTC-USD':{}},
                                      {'SEKNOK=X':{}}, {'unknown':{}}])
def test_unknown_or_continuous_instrument_keeps_strict_path(positions):
    assert routing._closed_held_exchanges(positions,at('2026-11-05T23:00:00')) is None


def test_open_exchange_keeps_strict_quote_path():
    assert routing._closed_held_exchanges({'EVO.ST':{}},at('2026-11-05T12:00:00')) is None


def test_verified_cached_closed_view_avoids_another_full_selection(monkeypatch):
    from services import restart_trading as trading, restart_read_reuse as reuse
    monkeypatch.setattr(trading,'current',lambda:None)
    monkeypatch.setattr(reuse,'cached_account_view',lambda family:{'status':'ACTIVE','positions':{'EVO.ST':{}}})
    monkeypatch.setattr(routing.control,'selected',lambda *args:pytest.fail('Redundant full bundle load'))
    assert routing.super_risk(at=at('2026-11-05T23:00:00'))['reason']=='MARKET_CLOSED'


@pytest.mark.parametrize('when,closed', [('2026-11-05T23:00:00',True),('2026-11-05T12:00:00',False)])
def test_closed_deferral_never_requests_quotes_or_mutates_journal(monkeypatch,when,closed):
    from services import restart_trading as trading
    chosen={'bundle':{'accounts':{'super_portfolio':{'account':{'positions':{'EVO.ST':{}}}}}}}
    original=deepcopy(chosen)
    monkeypatch.setattr(trading,'current',lambda:None)
    monkeypatch.setattr(routing.control,'selected',lambda family:chosen)
    monkeypatch.setattr(routing,'completed',lambda *args:None)
    def blocked(*args,**kwargs):raise ValueError('stale quote remains rejected')
    monkeypatch.setattr(routing,'context',blocked)
    monkeypatch.setattr(trading,'run',lambda **kwargs:pytest.fail('Unexpected journal mutation'))
    if closed:assert routing.super_risk(at=at(when))['reason']=='MARKET_CLOSED'
    else:
        with pytest.raises(ValueError,match='stale quote'):routing.super_risk(at=at(when))
    assert chosen==original


@pytest.mark.parametrize('scheduled,when,deferred',[(True,'2026-11-06T00:00:00',True),
                                                  (True,'2026-11-06T09:00:00',False),
                                                  (False,'2026-11-06T00:00:00',False)])
def test_scheduled_research_can_finish_off_hours_without_claiming_rebalance(monkeypatch,scheduled,when,deferred):
    from services import restart_trading as trading
    chosen={'approval':{},'bundle':{'accounts':{'super_portfolio':{'account':{'positions':{'EVO.ST':{}}}}}}}
    original=deepcopy(chosen)
    class Clock(datetime):
        @classmethod
        def now(cls,tz=None):return at(when)
    monkeypatch.setattr(routing,'datetime',Clock)
    monkeypatch.setattr(trading,'current',lambda:None)
    monkeypatch.setattr(routing.control,'selected',lambda *args,**kwargs:chosen)
    monkeypatch.setattr(routing,'completed',lambda *args:None)
    def stale(*args,**kwargs):raise ValueError('Fresh execution quote still required')
    monkeypatch.setattr(routing,'context',stale)
    monkeypatch.setattr(trading,'super_portfolio',lambda **kwargs:pytest.fail('Unexpected journal write'))
    pipeline={'run_id':'verified-research','market_activation_levels':{'USA':'PRODUCTION'},'candidates':[]}
    if deferred:
        result=routing.super_portfolio(pipeline,'AUTO',scheduled=scheduled)
        assert result['execution_state']=='DEFERRED_MARKET_CLOSED' and result['changes']==[]
    else:
        with pytest.raises(ValueError,match='Fresh execution'):routing.super_portfolio(pipeline,'AUTO',scheduled=scheduled)
    assert chosen==original
