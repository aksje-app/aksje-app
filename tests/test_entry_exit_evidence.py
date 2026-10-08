from copy import deepcopy
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

from exit_policy import evaluate_exit
from paper_entry_confirmation import observe_entry, entry_is_confirmed
from paper_risk_policy import strict_profit_protection_levels
from scanner_fresh_quote import validate_execution_quote
from super_portfolio import dynamic_stop_levels

NOW = datetime(2026, 10, 8, 12, tzinfo=timezone.utc)


def quote(at=NOW, price=100):
    return {"price": price, "market_data_at": at.isoformat(),
            "source": "yfinance 5m Close", "adjustment": "raw"}


class MemoryStorage:
    def __init__(self):
        self.value = {}

    def mutate_json(self, key, transform, default=None):
        self.value = transform(deepcopy(self.value))
        return deepcopy(self.value)


def observation(storage, at, run, *, signal="BUY", price=100):
    return observe_entry("AAA", {"signal": signal, "score": 8, "confidence": 80},
                         quote(at, price), run, min_score=7.2, min_confidence=70,
                         storage=storage, now=at)


def test_confirmation_requires_new_run_and_new_market_data_and_survives_restart():
    storage = MemoryStorage()
    first = observation(storage, NOW, "R1")
    assert not entry_is_confirmed("AAA", quote(), first, now=NOW)
    # A new cron process seeing the same bar cannot confirm.
    same = observation(storage, NOW, "R2")
    assert not entry_is_confirmed("AAA", quote(), same, now=NOW)
    later = NOW + timedelta(minutes=15)
    second = observation(storage, later, "R3")
    assert entry_is_confirmed("AAA", quote(later), second, now=later)
    assert not entry_is_confirmed("BBB", quote(later), second, now=later)
    assert not entry_is_confirmed("AAA", quote(later, 101), second, now=later)


def test_nonbuy_resets_confirmation_and_expiration_needs_two_new_checks():
    storage = MemoryStorage()
    observation(storage, NOW, "R1")
    observation(storage, NOW + timedelta(minutes=15), "R2", signal="HOLD")
    pending = observation(storage, NOW + timedelta(minutes=30), "R3")
    assert pending["status"] == "WAITING"
    expired = observation(storage, NOW + timedelta(minutes=160), "R4")
    assert expired["status"] == "WAITING"


@pytest.mark.parametrize("change", ["stale", "future", "naive", "adjusted", "wrong_price", "missing"])
def test_invalid_quote_never_becomes_execution(change):
    q = quote()
    if change == "stale": q = quote(NOW - timedelta(minutes=16))
    if change == "future": q = quote(NOW + timedelta(minutes=2))
    if change == "naive": q["market_data_at"] = NOW.replace(tzinfo=None).isoformat()
    if change == "adjusted": q["adjustment"] = "adjusted"
    if change == "wrong_price": q["price"] = 99
    if change == "missing": q = {}
    assert not validate_execution_quote(100, {"execution_quote": q, "market_data_at": q.get("market_data_at")}, now=NOW)[0]


def test_old_bar_cannot_move_position_backwards():
    assert not validate_execution_quote(100, {"execution_quote": quote(), "market_data_at": NOW.isoformat()},
                                        now=NOW, not_before=(NOW + timedelta(minutes=1)).isoformat())[0]


@pytest.mark.parametrize("peak,retention", [(101.9, 0), (102, 40), (103, 55), (105, 65), (106, 70), (108.4, 70)])
def test_all_three_engines_share_profit_tiers(peak, retention):
    paper = strict_profit_protection_levels({"entry_price": 100, "highest_price": peak, "last_price": peak})
    super_levels = dynamic_stop_levels({"entry_price": 100, "peak_price": peak})
    autonomy = evaluate_exit(entry_price=100, current_price=peak, highest_price=peak)
    for levels in (paper, super_levels, autonomy):
        assert levels["profit_retention_pct"] == retention
        assert levels["effective_stop_price"] == paper["effective_stop_price"]


def test_vei_profit_floor_sells_before_gain_is_lost():
    result = evaluate_exit(entry_price=202, current_price=213.8, highest_price=219)
    assert result["action"] == "SELL"
    assert result["reason_code"] == "PROFIT_PROTECT"
    assert result["effective_stop_price"] == 213.9


def engine(monkeypatch, portfolio):
    import trading_engine as te
    state = deepcopy(portfolio)
    notifications = []
    monkeypatch.setattr(te, "check_paper_trade", lambda *a, **kw: SimpleNamespace(allowed=True, run_id="TEST"))
    monkeypatch.setattr(te, "load_portfolio", lambda: deepcopy(state))
    monkeypatch.setattr(te, "load_rules", lambda: {"min_buy_confidence": 70, "position_size_pct": 10})
    monkeypatch.setattr(te, "save_portfolio", lambda p: state.update(deepcopy(p)))
    def add(p, trade):
        trade["time"] = datetime.now().isoformat()
        p["trades"].insert(0, trade)
        state.update(deepcopy(p))
    monkeypatch.setattr(te, "add_trade", add)
    monkeypatch.setattr(te, "build_paper_state_snapshot", lambda *a, **kw: {})
    monkeypatch.setattr(te, "audit_state_transition", lambda *a, **kw: None)
    monkeypatch.setattr(te, "record_paper_trade", lambda *a, **kw: None)
    monkeypatch.setattr(te, "notify_executed_trade", lambda *a, **kw: notifications.append(kw))
    monkeypatch.setattr(te, "_settings_bool", lambda *a: True)
    return te, state, notifications


def test_nohal_gap_sale_uses_observed_price_and_preserves_trigger_and_elapsed_time(monkeypatch):
    current = datetime.now(timezone.utc)
    te, state, alerts = engine(monkeypatch, {"cash": 0, "trades": [], "positions": {"NOHAL.OL": {
        "entry_price": 29.8, "shares": 100, "last_price": 29.8, "highest_price": 29.8,
        "opened_at": (current - timedelta(minutes=58)).isoformat(), "entry_score": 8,
        "confidence": 74}}})
    q = quote(current, 28.2)
    ok, _ = te.auto_trade("NOHAL.OL", 28.2, "HOLD", trade_context={"execution_quote": q,
                         "market_data_at": q["market_data_at"], "current_score": 7.5})
    assert ok and not state["positions"]
    trade = state["trades"][0]
    assert trade["price"] == 28.2 and trade["stop_trigger_price"] == 28.906
    assert trade["pnl_pct"] == -5.37
    assert trade["execution_gap_pct"] < -2
    assert trade["holding_minutes"] == 58
    assert alerts[0]["entry_score"] == 8


def test_stale_quote_blocks_risk_sale_before_any_state_change(monkeypatch):
    te, state, alerts = engine(monkeypatch, {"cash": 0, "trades": [], "positions": {
        "AAA": {"entry_price": 100, "shares": 10, "last_price": 100, "highest_price": 100}}})
    before = deepcopy(state)
    q = quote(datetime.now(timezone.utc) - timedelta(days=1), 94)
    ok, _ = te.auto_trade("AAA", 94, "SELL", trade_context={"execution_quote": q, "market_data_at": q["market_data_at"]})
    assert not ok and state == before and not alerts


def test_buy_requires_confirmation_and_saves_actual_entry_evidence(monkeypatch):
    current = datetime.now(timezone.utc)
    te, state, _ = engine(monkeypatch, {"cash": 10000, "positions": {}, "trades": []})
    monkeypatch.setattr(te, "validate_buy_order", lambda *a, **kw: (True, ""))
    monkeypatch.setattr(te, "_reentry_block_v1931ay", lambda *a, **kw: (False, ""))
    monkeypatch.setattr(te, "_automatic_repeat_buy_block_v1931ay", lambda *a, **kw: (False, ""))
    storage = MemoryStorage()
    observation(storage, current - timedelta(minutes=15), "FIRST")
    proof = observation(storage, current, "SECOND")
    q = quote(current)
    ctx = {"automatic": True, "execution_quote": q, "market_data_at": q["market_data_at"], "current_score": 8}
    assert not te.paper_buy("AAA", 100, 80, trade_context=ctx)[0]
    assert not state["positions"]
    outcome = te.paper_buy("AAA", 100, 80, trade_context={**ctx, "entry_confirmation": proof})
    assert outcome[0], (outcome, proof)
    assert state["positions"]["AAA"]["entry_score"] == 8
    assert state["positions"]["AAA"]["entry_confirmation"]["samples"] == proof["samples"]
    assert state["trades"][0]["execution_quote"] == q


def test_notification_does_not_turn_missing_score_into_zero(monkeypatch):
    import notifier
    messages = []
    monkeypatch.setattr(notifier, "send_pushover_alert", lambda message, **kw: messages.append(message))
    monkeypatch.setattr(notifier, "_paper_trade_alerts_enabled", lambda: True, raising=False)
    notifier.notify_trade("SELL", "AAA", 99, entry_score=None, exit_score=7.5, holding_days=0, holding_minutes=58)
    assert "Ikke registrert → 7.5" in messages[0]
    assert "58 minutter" in messages[0]


def scanner_trade_branch(storage, q, *, replacement_ok=False):
    """Execute the actual scanner trade branch with isolated IO, no network."""
    import ast
    from pathlib import Path
    source = ast.parse((Path(__file__).parents[1] / "scanner_worker.py").read_text())
    branch = next(node for node in ast.walk(source) if isinstance(node, ast.If)
                  and ast.unparse(node.test) == "paper_gate.allowed and auto_trading_enabled")
    module = ast.parse("def execute(result):\n    trades_executed = 0\n    for ticker in [result['ticker']]:\n        pass\n")
    module.body[0].body[1].body = [branch]
    calls = []
    env = {"paper_gate": SimpleNamespace(allowed=True), "auto_trading_enabled": True,
           "latest_prices": {}, "min_buy_score": 7.2, "min_buy_confidence": 70,
           "scan_run_id": "NEXT", "load_scanner_status": lambda: {"execution_id": "EX"},
           "load_portfolio": lambda: {"positions": {"OLD": {}}, "cash": 1000},
           "load_rules": lambda: {"max_open_positions": 1},
           "fresh_paper_buy_quote": lambda *a, **kw: (q, ""),
           "observe_entry": lambda *a, **kw: observe_entry(*a, **kw, storage=storage),
           "entry_is_confirmed": entry_is_confirmed,
           "_paper_candidate_context": lambda result: result,
           "_paper_replay_snapshot": lambda *a: {},
           "check_paper_trade": lambda *a, **kw: SimpleNamespace(allowed=True),
           "select_replacement_position": lambda *a, **kw: {"ticker": "OLD", "score": 7, "score_advantage": 1},
           "paper_sell": lambda *a, **kw: (calls.append("sell") or replacement_ok, "result"),
           "paper_buy": lambda *a, **kw: (calls.append("buy") or True, "result")}
    exec(compile(ast.fix_missing_locations(module), "scanner_trade_fixture", "exec"), env)
    env["execute"]({"ticker": "AAA", "price": q["price"], "score": 8, "signal": "BUY", "confidence": 80})
    return calls


def test_unconfirmed_candidate_cannot_sell_incumbent_to_make_room():
    assert scanner_trade_branch(MemoryStorage(), quote(datetime.now(timezone.utc))) == []


def test_failed_replacement_cannot_buy_beyond_slot_limit():
    now = datetime.now(timezone.utc)
    storage = MemoryStorage()
    observation(storage, now - timedelta(minutes=15), "FIRST")
    assert scanner_trade_branch(storage, quote(now)) == ["sell"]


def test_confirmed_candidate_replaces_only_after_successful_sale():
    now = datetime.now(timezone.utc)
    storage = MemoryStorage()
    observation(storage, now - timedelta(minutes=15), "FIRST")
    assert scanner_trade_branch(storage, quote(now), replacement_ok=True) == ["sell", "buy"]


def test_profit_floor_overrides_improving_score_and_cash_review():
    decision = evaluate_exit(entry_price=100, current_price=100.7, highest_price=102,
                             entry_score=70, current_score=74, holding_days=31)
    assert decision["action"] == "SELL" and decision["reason_code"] == "PROFIT_PROTECT"


def test_freshness_converts_quote_timezone_instead_of_dropping_offset():
    import trading_engine as te
    local = NOW.astimezone(timezone(timedelta(hours=-3)))
    assert te._automatic_signal_fresh_v1931ay({"automatic": True, "market_data_at": local.isoformat()}, {}, now=NOW)[0]


def test_autonomy_secures_gain_on_confirmed_fall_near_profit_floor():
    initial = evaluate_exit(entry_price=100, current_price=104.5, highest_price=105)
    result = evaluate_exit(entry_price=100, current_price=103.7, highest_price=105,
                           previous_stop_distance_pct=initial["distance_to_effective_stop_pct"])
    assert result["action"] == "SELL" and result["reason_code"] == "CONFIRMED_PROFIT_PROTECTION_EXIT"
    # One sample alone cannot establish a falling direction.
    assert evaluate_exit(entry_price=100, current_price=103.7, highest_price=105)["action"] == "HOLD"
