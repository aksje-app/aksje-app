"""Regression scenarios from the October 2026 production audit.

DNO's recorded entry/exit are reproduced. BWE/OMC execution prices below are
explicit scenario inputs: the production ZIPs did not retain their sale prices.
No test contacts production or sends notifications.
"""
from copy import deepcopy
from dataclasses import asdict
from datetime import datetime, timedelta, timezone
import json

import pytest

import super_portfolio as sp
from services import super_portfolio_store as journal
from services.storage_service import StorageService
from services.super_portfolio_accounting import settle
from trade_time import elapsed_hours, minimum_hold_met

NOW = datetime(2026, 10, 21, 8, 0, 49, tzinfo=timezone.utc)


def quote(price, at=NOW):
    return {"price": price, "market_data_at": at.isoformat(), "source": "yfinance 5m Close", "adjustment": "raw"}


def position(ticker, entry, last, peak):
    return {"ticker": ticker, "market": "Norge", "entry_date": "2026-10-20T13:10:38+00:00",
            "entry_price": entry, "last_price": last, "peak_price": peak, "target_weight_pct": 15,
            "position_id": ticker + ":audit-fixture"}


@pytest.fixture
def runtime(monkeypatch, tmp_path):
    storage = StorageService(tmp_path / "storage", database_url="", mode="local")
    monkeypatch.setattr(journal, "get_storage_service", lambda: storage)
    monkeypatch.setattr(sp, "load_state", lambda: deepcopy(storage.read_json(journal.STATE_KEY, {})))
    monkeypatch.setattr(sp, "append_event", lambda *a, **kw: None)
    cfg = sp.SuperPortfolioConfig(auto_pushover=False)
    state = sp.default_state(cfg)
    state["config"] = asdict(cfg)
    return storage, state


def test_bwe_omc_stop_settles_cash_nav_and_durable_rows(runtime, monkeypatch):
    storage, state = runtime
    state["portfolio_value"] = 974028.35
    state["positions"] = {"BWE.OL": position("BWE.OL", 69, 69.1, 69.3),
                          "OMC.OL": position("OMC.OL", 39.6, 39, 39.7)}
    storage.write_json(journal.STATE_KEY, state)
    # Scenario quotes, not reconstructed historical production fills.
    monkeypatch.setattr(sp, "_execution_quotes", lambda *a: {"BWE.OL": quote(66), "OMC.OL": quote(37)})
    result = sp.run_lightweight_stop_surveillance(now=NOW)
    saved = storage.read_json(journal.STATE_KEY)
    proceeds = 974028.35 * .15 * (66 / 69.1 + 37 / 39)
    expected = 974028.35 * .7 + proceeds * .999
    assert not saved["positions"]
    assert saved["cash"] == pytest.approx(expected, abs=.00001)
    assert saved["portfolio_value"] == round(expected, 2)
    assert saved["transaction_cost"] == pytest.approx(proceeds * .001)
    fresh_process = StorageService(storage.base_dir, database_url="", mode="local")
    rows = journal.transactions(fresh_process)
    assert {r["ticker"] for r in rows} == {"BWE.OL", "OMC.OL"}
    for row in rows:
        assert row["trade_id"] and row["reason_code"] and row["stop_price"]
        assert row["price_observed_at"] == NOW.isoformat()
        assert row["decision_at"] == row["simulated_execution_at"] == NOW.isoformat()
        assert row["entry_at"] == "2026-10-20T13:10:38+00:00"
    # Replaying a stale pre-sale state cannot append a second sale or lose cash.
    sp.run_lightweight_stop_surveillance(state=state, now=NOW)
    assert journal.transactions(fresh_process) == rows
    assert storage.read_json(journal.STATE_KEY)["cash"] == saved["cash"]
    assert len(result["changes"]) == 2


def test_dno_risk_exit_remains_immediate_inside_minimum_hold(runtime, monkeypatch):
    storage, state = runtime
    now = datetime(2026, 10, 21, 1, 10, 24, tzinfo=timezone.utc)
    state["positions"] = {"DNO.OL": position("DNO.OL", 22.4200000763, 23.44, 23.4400005341)}
    storage.write_json(journal.STATE_KEY, state)
    monkeypatch.setattr(sp, "_execution_quotes", lambda *a: {"DNO.OL": quote(22.2999992371, now)})
    result = sp.run_lightweight_stop_surveillance(now=now)
    trade = result["changes"][0]
    assert trade["reason_code"] == "PROFIT_PROTECTION_EXIT"
    assert trade["execution_price"] == 22.2999992371
    assert trade["stop_price"] == pytest.approx(22.981)
    assert elapsed_hours(trade["entry_at"], now) < 24
    assert len(journal.transactions(storage)) == 1


@pytest.mark.parametrize("bad", [None, "stale", "future", "missing_time", "nan"])
def test_missing_or_stale_quotes_never_execute(runtime, monkeypatch, bad):
    storage, state = runtime
    state["positions"] = {"BWE.OL": position("BWE.OL", 69, 69, 69)}
    storage.write_json(journal.STATE_KEY, state)
    q = quote(50)
    if bad == "stale": q = quote(50, NOW - timedelta(minutes=16))
    if bad == "future": q = quote(50, NOW + timedelta(minutes=2))
    if bad == "missing_time": q.pop("market_data_at")
    if bad == "nan": q["price"] = float("nan")
    monkeypatch.setattr(sp, "_execution_quotes", lambda *a, **k: {} if bad is None else {"BWE.OL": q})
    result = sp.run_lightweight_stop_surveillance(now=NOW)
    saved = storage.read_json(journal.STATE_KEY)
    assert not result["changes"] and not journal.transactions(storage)
    assert saved["positions"]["BWE.OL"]["last_price"] == 69


def test_cash_nav_reconcile_after_each_partial_and_full_sale():
    before = {"portfolio_value": 1000, "initial_cash": 1000, "positions": {
        "AAA": {**position("AAA", 100, 100, 100), "target_weight_pct": 50}}}
    keep = {"AAA": {**before["positions"]["AAA"], "target_weight_pct": 25, "last_price": 110}}
    first = settle(before, keep, [{"ticker": "AAA", "action": "REDUCE", "from_pct": 50, "to_pct": 25,
                                  "execution_price": 110}], operation_id="one", decision_at=NOW.isoformat(), cost_bps=10)
    assert first["cash"] == pytest.approx(774.725)
    assert first["portfolio_value"] == round(first["cash"] + first["positions"]["AAA"]["market_value"], 2)
    second = settle({**before, **first}, {}, [{"ticker": "AAA", "action": "SELL", "from_pct": 25, "to_pct": 0,
                                            "exit_price": 110}], operation_id="two", decision_at=NOW.isoformat(), cost_bps=10)
    assert second["cash"] == pytest.approx(1049.45)
    assert second["portfolio_value"] == round(second["cash"], 2)


def test_storage_conflict_and_same_operation_never_duplicate(runtime):
    storage, state = runtime
    first = journal.commit(state, operation_id="job:SPJ-20261021-131559-9C8E27", trades=[{"trade_id": "one"}], storage=storage)
    repeated = journal.commit(state, operation_id="job:SPJ-20261021-131559-9C8E27", trades=[{"trade_id": "two"}], storage=storage)
    assert repeated["_revision"] == first["_revision"]
    assert repeated["cash"] == first["cash"]
    assert journal.transactions(storage) == [{"trade_id": "one"}]
    with pytest.raises(journal.PortfolioConflict):
        journal.commit(state, operation_id="different-job", trades=[{"trade_id": "bad"}], storage=storage)
    assert len(journal.transactions(storage)) == 1


def test_audited_legacy_failed_job_is_recovered_without_invented_trades(runtime):
    storage, state = runtime
    job_id = "SPJ-20261021-131559-9C8E27"
    run_id = "SPM-20261021-131600"
    changes = [{"action": "BUY", "ticker": "MEDI.OL"}, {"action": "BUY", "ticker": "AKRBP.OL"}]
    state.update(source_run_id=run_id, history=[{"source_run_id": run_id, "changes": changes}])
    storage.write_json(journal.STATE_KEY, state)
    storage.write_json("super_portfolio/market_pipeline.json", {"job_id": job_id, "run_id": run_id, "verification": {"ok": True}})
    saved = journal.committed_job(job_id, storage)
    assert saved["legacy_commit_verified"]
    assert saved["changes"] == changes
    assert journal.transactions(storage) == []  # missing historical prices are never reconstructed
    assert journal.committed_job(job_id, storage) == saved


def test_legacy_job_recovery_requires_matching_persisted_evidence(runtime):
    storage, state = runtime
    storage.write_json(journal.STATE_KEY, state)
    storage.write_json("super_portfolio/market_pipeline.json", {"job_id": "J", "run_id": "R", "verification": {"ok": True}})
    assert journal.committed_job("J", storage) is None


def test_legacy_unknown_commit_status_never_rescans(runtime, monkeypatch):
    from contextlib import nullcontext
    import super_portfolio_worker as worker
    storage, _ = runtime
    status = {"job_id": "old-job", "state": "FAILED", "error": "TypeError: object of type 'int' has no len()"}
    monkeypatch.setattr(worker.jobs, "worker_execution_lease", lambda *a: nullcontext())
    monkeypatch.setattr(worker.jobs, "get_job", lambda *a: dict(status))
    monkeypatch.setattr(worker.jobs, "update_job", lambda *a, **kw: {**status, **kw})
    monkeypatch.setattr(worker, "_build_pipeline", lambda **kw: pytest.fail("An unknown historical commit must not be executed again"))
    result = worker.run_claimed_job.__wrapped__("old-job", "test-only")
    assert result["state"] == "INTERRUPTED"
    assert result["failure_type"] == "COMMIT_STATUS_UNKNOWN"
    assert not journal.transactions(storage)


def test_export_has_full_journal_and_explicit_historical_gap(runtime):
    storage, state = runtime
    rows = [{"trade_id": str(i), "decision_at": NOW.isoformat(), "ticker": "DNO.OL", "action": "SELL"} for i in range(301)]
    journal.commit(state, operation_id="export", trades=rows, storage=storage)
    files = journal.export_files(storage)
    assert len(json.loads(files["transactions.json"])) == 301
    assert len(files["transactions.csv"].splitlines()) == 302
    assert json.loads(files["transaction_coverage.json"])["historical_coverage"] == "UNKNOWN_BEFORE_ACCOUNTING_OPENING_BALANCE"


def test_hold_time_uses_offsets_and_missing_time_fails_closed(monkeypatch):
    import trading_engine as te
    from trade_time import utc_time
    now = datetime.now(timezone.utc)
    recent = (now - timedelta(hours=2)).astimezone(timezone(timedelta(hours=2)))
    assert not te._auto_sell_hold_guard_v18675({"opened_at": recent.isoformat()}, {"minimum_hold_hours": 24})[0]
    assert not te._auto_sell_hold_guard_v18675({}, {"minimum_hold_hours": 24})[0]
    assert not minimum_hold_met({"entry_date": "broken"}, 24)
    assert elapsed_hours("2026-10-21T12:00:00+02:00", NOW) is None  # future
    assert utc_time("2026-10-21T10:00:00") == datetime(2026, 10, 21, 10, tzinfo=timezone.utc)


def test_latest_sell_not_oldest_controls_reentry():
    import trading_engine as te
    now = datetime.now(timezone.utc)
    trades = [{"type": "SELL", "ticker": "DNO.OL", "time": (now - timedelta(hours=1)).isoformat()},
              {"type": "SELL", "ticker": "DNO.OL", "time": (now - timedelta(days=30)).isoformat()}]
    assert te._reentry_block_v1931ay({"trades": trades}, "DNO.OL", 80, {"sell_signal_cooldown_days": 5})[0]


def test_signal_hold_does_not_disable_stop_or_profit_protection():
    from exit_policy import evaluate_exit
    assert evaluate_exit(entry_price=100, current_price=100, highest_price=100, current_score=50, holding_hours=2)["reason_code"] == "MINIMUM_HOLD"
    assert evaluate_exit(entry_price=100, current_price=100, highest_price=100, current_score=50, holding_hours=25)["reason_code"] == "SCORE_EXIT"
    assert evaluate_exit(entry_price=100, current_price=114, highest_price=114, current_score=50, holding_hours=25)["reason_code"] == "SCORE_EXIT"
    assert evaluate_exit(entry_price=100, current_price=114, highest_price=114, current_score=50, holding_hours=2)["reason_code"] == "TAKE_PROFIT_PARTIAL"
    assert evaluate_exit(entry_price=100, current_price=94, highest_price=100, holding_hours=0)["action"] == "SELL"
    assert evaluate_exit(entry_price=100, current_price=100.8, highest_price=102, holding_hours=0)["action"] == "SELL"
    assert elapsed_hours("2026-10-25T02:30:00+02:00", datetime.fromisoformat("2026-10-25T02:30:00+01:00")) == 1


def candidate(ticker, score):
    return {"ticker": ticker, "investment_score": score, "risk_score": 20, "data_quality_score": 95,
            "price": 100, "sector": "Technology", "market": "USA",
            "raw": {"last_price": 100, "volatility_pct": 20, "return_20d": 3}}


def test_ordinary_super_portfolio_sale_waits_for_24_hours(runtime):
    storage, state = runtime
    state["config"]["target_positions"] = 1
    state["candidate_persistence"] = {"NEW": {"streak": 3, "last_run_id": "older"}}
    state["positions"] = {"KEEP": {**position("KEEP", 100, 100, 100), "market": "USA",
                                  "entry_date": (NOW - timedelta(hours=2)).isoformat()}}
    storage.write_json(journal.STATE_KEY, state)
    pipeline = {"run_id": "young", "created_at": NOW.isoformat(), "candidates": [candidate("NEW", 99), candidate("KEEP", 65)]}
    blocked = sp.evaluate(pipeline=pipeline, now=NOW, persist=False, rebalance_policy="FORCE")
    assert set(blocked["state"]["positions"]) == {"KEEP"}
    assert not blocked["changes"]
    assert "MINIMUM_HOLD" in blocked["rebalance_gate"]["reason_codes"]
    state["positions"]["KEEP"]["entry_date"] = (NOW - timedelta(hours=25)).isoformat()
    storage.write_json(journal.STATE_KEY, state)
    allowed = sp.evaluate(pipeline={**pipeline, "run_id": "mature"}, now=NOW, persist=False, rebalance_policy="FORCE")
    assert {c["action"] for c in allowed["changes"]} == {"BUY", "SELL"}


def test_one_approved_refill_slot_cannot_buy_three(runtime, monkeypatch):
    storage, state = runtime
    state["positions"] = {"KEEP": {**position("KEEP", 100, 100, 100), "market": "USA"}}
    state["pending_risk_refill_slots"] = 1
    state["candidate_persistence"] = {t: {"streak": 2, "last_run_id": "old"} for t in ["BWE.OL", "OMC.OL", "DNO.OL"]}
    storage.write_json(journal.STATE_KEY, state)
    result = sp.evaluate(pipeline={"run_id": "refill-regression", "created_at": NOW.isoformat(),
                        "candidates": [candidate(t, score) for t, score in [("KEEP", 99), ("BWE.OL", 90), ("OMC.OL", 89), ("DNO.OL", 88)]]},
                        persist=False, now=NOW, rebalance_policy="AUTO")
    buys = [r for r in result["changes"] if r["action"] == "BUY"]
    assert len(buys) == 1
    assert result["state"]["pending_risk_refill_slots"] == 0


def test_untimed_candidate_cannot_be_booked_as_fresh_purchase(runtime, monkeypatch):
    storage, state = runtime
    storage.write_json(journal.STATE_KEY, state)
    monkeypatch.setattr(sp, "_execution_quotes", lambda *a, **k: {})
    result = sp.evaluate(pipeline={"run_id": "missing-price-evidence", "created_at": NOW.isoformat(),
                                 "candidates": [candidate("DNO.OL", 90)]}, now=NOW, persist=True)
    assert result["changes"] == []
    assert journal.transactions(storage) == []


def test_full_evaluation_can_stop_without_a_new_analytical_candidate(runtime, monkeypatch):
    storage, state = runtime
    state["positions"] = {"DNO.OL": position("DNO.OL", 22.42, 23.44, 23.44)}
    storage.write_json(journal.STATE_KEY, state)
    monkeypatch.setattr(sp, "_execution_quotes", lambda *a: {"DNO.OL": quote(22.3)})
    result = sp.evaluate(pipeline={"run_id": "risk-only", "created_at": NOW.isoformat(), "candidates": []},
                         now=NOW, persist=True, rebalance_policy="AUTO")
    assert len(result["changes"]) == 1
    assert result["changes"][0]["execution_price"] == 22.3
    assert not storage.read_json(journal.STATE_KEY)["positions"]
    repeated = sp.evaluate(pipeline={"run_id": "risk-only", "created_at": NOW.isoformat(), "candidates": []},
                           now=NOW, persist=True)
    assert repeated["already_committed"]
    assert len(journal.transactions(storage)) == 1


@pytest.mark.parametrize("fail_publication", [False, True])
def test_scheduled_sp_job_with_committed_trades_is_not_executed_twice(runtime, monkeypatch, fail_publication):
    from contextlib import nullcontext
    import super_portfolio_worker as worker
    storage, state = runtime
    storage.write_json(journal.STATE_KEY, state)
    job_id = "SPJ-20261021-131559-9C8E27"
    status = {"job_id": job_id, "execution_token": "test-only", "trigger": "SCHEDULED", "state": "QUEUED"}
    monkeypatch.setattr(worker.jobs, "worker_execution_lease", lambda *a: nullcontext())
    monkeypatch.setattr(worker.jobs, "get_job", lambda *a: dict(status))
    monkeypatch.setattr(worker.jobs, "_require_worker", lambda *a: None)
    def update(job_id, token, **changes):
        status.update(changes)
        return dict(status)
    monkeypatch.setattr(worker.jobs, "update_job", update)
    monkeypatch.setattr(worker.jobs, "append_progress", lambda *a: None)
    pipeline = {"run_id": "SPM-20261021-131600", "job_id": job_id, "candidates": [{"ticker": "MEDI.OL"}],
                "outcome": "COMPLETED", "verification": {"ok": True}}
    calls = []
    monkeypatch.setattr(worker, "_build_pipeline", lambda **k: calls.append("build") or pipeline)
    def evaluate(**kwargs):
        changes = [{"trade_id": "medi", "action": "BUY", "ticker": "MEDI.OL"},
                   {"trade_id": "akrbp", "action": "BUY", "ticker": "AKRBP.OL"}]
        saved = journal.commit(state, operation_id="job:" + job_id, trades=changes,
                               result={"run_id": pipeline["run_id"], "verification": {"ok": True}}, storage=storage)
        return {"state": saved, "changes": changes, "stop_alerts": []}
    monkeypatch.setattr(sp, "evaluate", evaluate)
    monkeypatch.setattr(sp, "refresh_index_benchmark", lambda *a, **k: {})
    monkeypatch.setattr(sp, "resource_health", lambda: {})
    publish = worker.publish_verified_result
    if fail_publication:
        monkeypatch.setattr(worker, "publish_verified_result", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("post-commit status failure")))
    first = worker.run_claimed_job.__wrapped__(job_id, "test-only")
    if fail_publication:
        assert first["state"] == "DEGRADED"
        assert first["portfolio_committed"]
        assert "lagret" in first["message"]
    else:
        assert first["state"] == "COMPLETED"
        assert first["applied_changes"] == 2
    monkeypatch.setattr(worker, "publish_verified_result", publish)
    again = worker.run_claimed_job.__wrapped__(job_id, "test-only")
    assert again["state"] == "COMPLETED" and again["already_committed"]
    assert calls == ["build"]
    assert len(journal.transactions(storage)) == 2
