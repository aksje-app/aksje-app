"""Independent review: actual exported opening balance and execution boundaries."""
from copy import deepcopy
from dataclasses import asdict
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path

import pandas as pd
import pytest

import scanner_fresh_quote as quotes
import super_portfolio as sp
from services import super_portfolio_store as journal
from services.storage_service import StorageService
from services.super_portfolio_accounting import settle

NOW = datetime(2026, 10, 22, 12, tzinfo=timezone.utc)


def pos(ticker, weight, price=100, currency="NOK"):
    return dict(ticker=ticker, target_weight_pct=weight, entry_price=price,
                last_price=price, peak_price=price, market="Norge", currency=currency,
                entry_date="2026-10-19T12:00:00+00:00")


@pytest.fixture
def local(monkeypatch, tmp_path):
    storage = StorageService(tmp_path, database_url="", mode="local")
    monkeypatch.setattr(journal, "get_storage_service", lambda: storage)
    monkeypatch.setattr(sp, "load_state", lambda: deepcopy(storage.read_json(journal.STATE_KEY, {})))
    monkeypatch.setattr(sp, "append_event", lambda *a, **kw: None)
    return storage


def feed(monkeypatch, prices, at):
    # Exercise the real quote fetch wrapper and both freshness validators.
    monkeypatch.setattr(quotes, "_intraday_history", lambda t: pd.DataFrame(
        {"Close": [prices[t]]}, index=pd.DatetimeIndex([at])))


def assert_balanced(result):
    assert result["portfolio_value"] == round(result["cash"] + sum(
        p["market_value"] for p in result["positions"].values()), 2)
    assert result["cash"] >= 0


@pytest.mark.parametrize("path",["stop", "full_evaluation"])
def test_exported_production_opening_is_unchanged_without_trades(local, monkeypatch,path):
    fixture = json.loads((Path(__file__).parent / "fixtures/super_portfolio_20261021_opening.json").read_text())
    state = fixture["state"]
    state["config"] = asdict(sp.SuperPortfolioConfig(auto_pushover=False))
    local.write_json(journal.STATE_KEY, state)
    feed(monkeypatch, {t:p["last_price"] for t,p in state["positions"].items()}, NOW)
    first = (sp.run_lightweight_stop_surveillance(now=NOW) if path=="stop" else
             sp.evaluate(pipeline={"run_id":"opening-no-trades","created_at":NOW.isoformat(),"candidates":[]},
                         persist=True,now=NOW))
    saved = local.read_json(journal.STATE_KEY)
    assert first["changes"] == []
    assert saved["portfolio_value"] == 973526.92
    assert saved["cash"] == pytest.approx(389410.768)
    assert saved["last_portfolio_transaction_cost"] == 0
    assert_balanced(saved)
    for ticker, old in state["positions"].items():
        assert all(saved["positions"][ticker][k] == v for k,v in old.items())
        assert saved["positions"][ticker]["market_value"] == pytest.approx(146029.038)
    assert journal.transactions(local) == []
    # A later no-trade run cannot reinitialize/rebase existing model units.
    later = NOW + timedelta(minutes=16)
    feed(monkeypatch, {t:p["last_price"] for t,p in state["positions"].items()}, later)
    sp.run_lightweight_stop_surveillance(now=later)
    second = local.read_json(journal.STATE_KEY)
    assert second["cash"] == saved["cash"]
    assert second["portfolio_value"] == saved["portfolio_value"]
    assert second["accounting_opening_balance"] == saved["accounting_opening_balance"]
    files = journal.export_files(local)
    assert json.loads(files["transactions.json"]) == []  # no invented BWE/OMC sales
    assert json.loads(files["transaction_coverage.json"])["historical_coverage"].startswith("UNKNOWN_BEFORE")
    assert json.loads(files["transaction_coverage.json"])["historical_return_fully_verified"] is False


def test_added_position_keeps_hold_reference_across_full_assessments():
    from trade_time import minimum_hold_met
    old={**pos("KEEP",15),"last_added_at":NOW.isoformat()}
    updated=sp._position_from_row({"ticker":"KEEP","price":100},15,old,
                                 (NOW+timedelta(hours=1)).isoformat(),sp.SuperPortfolioConfig(),[])
    assert updated["last_added_at"]==old["last_added_at"]
    assert not minimum_hold_met(updated,24,NOW+timedelta(hours=2))


def test_fully_invested_rotation_sells_before_funding_the_purchase():
    before = dict(initial_cash=1000, portfolio_value=1000, positions={"OLD":pos("OLD",100)})
    result = settle(before, {"NEW":pos("NEW",100)}, [
        dict(ticker="NEW",action="BUY",from_pct=0,to_pct=100,execution_price=100),
        dict(ticker="OLD",action="SELL",from_pct=100,to_pct=0,exit_price=100),
    ], operation_id="rotation", decision_at=NOW.isoformat(), cost_bps=10)
    assert [t["action"] for t in result["transactions"]] == ["SELL", "BUY"]
    assert result["cash"] == pytest.approx(0,abs=1e-6)
    assert result["portfolio_value"] == 998
    assert_balanced(result)


def test_buy_sell_reduce_and_add_in_one_settlement():
    before = dict(initial_cash=1000, portfolio_value=1000, positions={
        "A":pos("A",30), "B":pos("B",20), "D":pos("D",20,50)})
    output = {"B":{**pos("B",10),"last_price":90},"D":pos("D",25,50),"C":pos("C",20,20)}
    changes = [dict(ticker="C",action="BUY",from_pct=0,to_pct=20,execution_price=20),
               dict(ticker="D",action="ADD",from_pct=20,to_pct=25,execution_price=50),
               dict(ticker="B",action="REDUCE",from_pct=20,to_pct=10,execution_price=90),
               dict(ticker="A",action="SELL",from_pct=30,to_pct=0,exit_price=110)]
    result = settle(before, output, changes, operation_id="mixed",decision_at=NOW.isoformat(),cost_bps=10)
    assert result["cash"] == pytest.approx(469.33)
    assert result["transaction_cost"] == pytest.approx(.67)
    assert result["portfolio_value"] == 1009.33
    assert result["positions"]["B"]["quantity"] == 1
    assert result["positions"]["D"]["quantity"] == 5
    assert result["positions"]["D"]["last_added_at"] == NOW.isoformat()
    from trade_time import minimum_hold_met
    assert not minimum_hold_met(result["positions"]["D"],24,NOW+timedelta(hours=1))
    assert_balanced(result)
    # Independent running cash/exposure calculation for every journal row.
    cash, exposure = 300, 710  # marked A=330, B=180, D=200
    for row in result["transactions"]:
        signed = row["gross_amount"] * (1 if row["action"] in {"SELL","REDUCE"} else -1)
        cash += signed - row["transaction_cost"]
        exposure -= signed
        assert row["cash_after"] == pytest.approx(cash,abs=2e-6)
        assert row["portfolio_value_after"] == round(cash + exposure,2)


@pytest.mark.parametrize("age_minutes",[None,16,0])
def test_existing_position_add_requires_fresh_quote(local, monkeypatch,age_minutes):
    state = sp.default_state(sp.SuperPortfolioConfig(auto_pushover=False))
    state["positions"] = {"KEEP":pos("KEEP",10)}
    local.write_json(journal.STATE_KEY,state)
    row = dict(ticker="KEEP",market="Norge",price=100,investment_score=90,risk_score=10,
               portfolio_score=90,portfolio_score_adjusted=90,rank=1,sector="Technology")
    # Freeze an already approved decision; verify the execution guard separately
    # from ranking/persistence, which this review must not change.
    monkeypatch.setattr(sp,"rank_candidates", lambda *a,**k:[row])
    monkeypatch.setattr(sp,"select_target_rows_with_hysteresis",lambda *a,**k:([row],{}))
    monkeypatch.setattr(sp,"_candidate_entry_gates",lambda **k:([row],{},{}))
    monkeypatch.setattr(sp,"target_weights",lambda *a,**k:{"KEEP":15})
    monkeypatch.setattr(sp,"build_rebalance_gate",lambda **k:{"allowed":True,"reason_codes":[]})
    if age_minutes is None:
        monkeypatch.setattr(quotes,"_intraday_history",lambda *a:pd.DataFrame())
    else:
        feed(monkeypatch,{"KEEP":100},NOW-timedelta(minutes=age_minutes))
    result = sp.evaluate(pipeline={"run_id":"no-quote-add","created_at":NOW.isoformat(),"candidates":[row]},
                         persist=True,now=NOW,rebalance_policy="FORCE")
    if age_minutes == 0:
        assert [r["action"] for r in result["changes"]] == ["ADD"]
        assert local.read_json(journal.STATE_KEY)["positions"]["KEEP"]["last_added_at"]==NOW.isoformat()
        assert len(journal.transactions(local))==1
    else:
        assert result["changes"] == []
        assert "EXECUTION_QUOTE_UNAVAILABLE" in result["rebalance_gate"]["reason_codes"]
        assert journal.transactions(local) == []


@pytest.mark.parametrize("market,ticker,now,observed,executes", [
    ("Norge","DNO.OL",NOW,NOW,True),
    ("USA","OMC",datetime(2026,10,22,15,tzinfo=timezone.utc),datetime(2026,10,22,15,tzinfo=timezone.utc),True),
    ("Norge","DNO.OL",datetime(2026,10,22,20,tzinfo=timezone.utc),datetime(2026,10,22,14,20,tzinfo=timezone.utc),False),
    ("USA","OMC",datetime(2026,10,25,15,tzinfo=timezone.utc),datetime(2026,10,23,19,55,tzinfo=timezone.utc),False),
    ("Norge","DNO.OL",NOW,NOW-timedelta(minutes=16),False),
    # No market-open gate is added: the existing shadow stop can still use the
    # last regular-session raw bar while it passes the unchanged 15m checks.
    ("Norge","DNO.OL",datetime(2026,10,22,14,30,tzinfo=timezone.utc),datetime(2026,10,22,14,20,tzinfo=timezone.utc),True),
])
def test_stop_surveillance_real_quote_validation(local,monkeypatch,market,ticker,now,observed,executes):
    from market_hours import market_status
    state = sp.default_state(sp.SuperPortfolioConfig(auto_pushover=False))
    state["positions"] = {ticker:{**pos(ticker,15),"market":market,"entry_date":(now-timedelta(hours=1)).isoformat()}}
    local.write_json(journal.STATE_KEY,state)
    feed(monkeypatch,{ticker:90},observed)
    result = sp.run_lightweight_stop_surveillance(now=now)
    assert market_status(market,now=now)["is_open"] == (market=="USA" and now.weekday()<5 or market=="Norge" and now.hour==12)
    assert bool(result["changes"]) == executes
    saved=local.read_json(journal.STATE_KEY)
    assert len(journal.transactions(local)) == int(executes)
    if executes:
        assert result["changes"][0]["reason_code"] == "HARD_STOP"
        assert_balanced(saved)
    else:
        assert saved["positions"][ticker]["last_price"] == 100


def test_missing_provider_data_does_not_abort_or_invent_stop_price(local,monkeypatch):
    state=sp.default_state(sp.SuperPortfolioConfig(auto_pushover=False))
    state["positions"]={"DNO.OL":pos("DNO.OL",15)}
    local.write_json(journal.STATE_KEY,state)
    monkeypatch.setattr(quotes,"_intraday_history",lambda *a:pd.DataFrame())
    result=sp.run_lightweight_stop_surveillance(now=NOW)
    assert result["state"]=="NO_FRESH_PRICE"
    assert local.read_json(journal.STATE_KEY)["positions"]==state["positions"]
    assert not journal.transactions(local)


def test_missing_quote_for_one_position_does_not_block_another_stop(local,monkeypatch):
    state=sp.default_state(sp.SuperPortfolioConfig(auto_pushover=False))
    state["positions"]={"DNO.OL":pos("DNO.OL",15),"MISSING":pos("MISSING",15)}
    local.write_json(journal.STATE_KEY,state)
    feed(monkeypatch,{"DNO.OL":90},NOW)  # missing ticker raises at provider boundary
    result=sp.run_lightweight_stop_surveillance(now=NOW)
    assert [r["ticker"] for r in result["changes"]]==["DNO.OL"]
    saved=local.read_json(journal.STATE_KEY)
    assert saved["positions"]["MISSING"]["last_price"]==100
    assert_balanced(saved)


@pytest.mark.parametrize("currency",["NOK","USD","SEK","DKK","EUR"])
def test_existing_model_uses_local_price_ratios_without_fx_revaluation(currency):
    before=dict(initial_cash=1000,portfolio_value=1000,config={"base_currency":"NOK"},positions={"X":pos("X",50,100,currency)})
    initialized=settle(before,before["positions"],[],operation_id="start",decision_at=NOW.isoformat(),cost_bps=10)
    output=deepcopy(initialized["positions"]);output["X"]["last_price"]=110
    result=settle({**before,**initialized},output,[],operation_id="mark",decision_at=NOW.isoformat(),cost_bps=10)
    assert result["portfolio_value"]==1050  # identical for every quote currency
    assert result["positions"]["X"]["quantity"]==5  # model units, not foreign shares
    assert_balanced(result)
