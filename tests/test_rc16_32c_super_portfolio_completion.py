from datetime import datetime, timezone

import super_portfolio as sp


def _candidate(ticker, score=90, risk=30, price=100, sector="Tech", market="USA", vol=25, returns=None):
    raw = {"last_price": price, "volatility_pct": vol}
    for key, value in (returns or {}).items():
        raw[key] = value
    return {
        "ticker": ticker,
        "investment_score": score,
        "risk_score": risk,
        "data_quality_score": 90,
        "price": price,
        "sector": sector,
        "market": market,
        "raw": raw,
    }


def test_dynamic_stop_tightens_for_large_profit_and_widens_for_high_volatility():
    cfg = sp.SuperPortfolioConfig()
    high_vol = {"entry_price": 100, "peak_price": 110, "last_price": 105, "volatility_pct": 55}
    protected_profit = {"entry_price": 100, "peak_price": 165, "last_price": 155, "volatility_pct": 55}
    high_vol_levels = sp.dynamic_stop_levels(high_vol, cfg)
    protected_levels = sp.dynamic_stop_levels(protected_profit, cfg)
    assert high_vol_levels["hard_stop_drawdown_pct"] > cfg.hard_stop_drawdown_pct
    assert protected_levels["hard_stop_drawdown_pct"] <= 8.0
    assert protected_levels["hard_stop_drawdown_pct"] < high_vol_levels["hard_stop_drawdown_pct"]


def test_return_profile_correlations_are_derived_without_network_calls():
    rows = [
        sp._normalized_candidate(_candidate("AAA", returns={"return_1d": 1, "return_5d": 5, "return_20d": 10, "return_60d": 20})),
        sp._normalized_candidate(_candidate("BBB", returns={"return_1d": 1.1, "return_5d": 5.2, "return_20d": 10.5, "return_60d": 20.5})),
        sp._normalized_candidate(_candidate("CCC", returns={"return_1d": -1, "return_5d": 2, "return_20d": -3, "return_60d": 1})),
    ]
    enriched = sp.attach_return_profile_correlations(rows)
    by = {row["ticker"]: row for row in enriched}
    assert by["BBB"]["raw_candidate"]["portfolio_correlations"]["AAA"] > 0.95
    assert by["BBB"]["correlation_source"] == "MULTI_HORIZON_RETURN_PROFILE"
    assert by["CCC"]["raw_candidate"]["portfolio_correlations"]["AAA"] < 0.8


def test_manual_exit_creates_cooldown_and_evaluation_does_not_reenter(monkeypatch):
    cfg = sp.SuperPortfolioConfig(target_positions=2, manual_exit_cooldown_days=10)
    state = sp.default_state(cfg)
    state["positions"] = {"AAA": {"ticker": "AAA", "target_weight_pct": 50, "entry_price": 100, "last_price": 105, "peak_price": 110}}
    monkeypatch.setattr(sp, "load_state", lambda: state)
    monkeypatch.setattr(sp, "save_state", lambda value: state.update(value) or value)
    monkeypatch.setattr(sp, "append_event", lambda *a, **k: None)
    exit_result = sp.manual_exit("AAA", "Jeg går ut tidlig")
    assert exit_result["ok"] is True
    assert "AAA" in state["manual_exit_cooldown"]
    pipeline = {"run_id": "R1", "candidates": [_candidate("AAA", 99), _candidate("BBB", 95), _candidate("CCC", 90)]}
    result = sp.evaluate(pipeline=pipeline, persist=False, now=datetime(2026, 9, 14, tzinfo=timezone.utc))
    assert "AAA" not in result["state"]["positions"]
    assert any(row["ticker"] == "AAA" for row in result["state"].get("manual_exit_shadow", []))


def test_daily_analysis_preserves_weights_until_weekly_rebalance(monkeypatch):
    cfg = sp.SuperPortfolioConfig(target_positions=2, rebalance_weekday=4)
    state = sp.default_state(cfg)
    state["positions"] = {
        "AAA": {"ticker":"AAA","market":"USA","sector":"Tech","target_weight_pct":60.0,"entry_price":100,"last_price":100,"peak_price":100,"risk_score":30,"portfolio_score":90},
        "BBB": {"ticker":"BBB","market":"USA","sector":"Health","target_weight_pct":40.0,"entry_price":100,"last_price":100,"peak_price":100,"risk_score":30,"portfolio_score":85},
    }
    monkeypatch.setattr(sp, "load_state", lambda: state)
    pipeline = {"run_id":"MONDAY", "candidates":[_candidate("CCC",99), _candidate("AAA",80), _candidate("BBB",79)]}
    result = sp.evaluate(pipeline=pipeline, persist=False, now=datetime(2026,9,14,tzinfo=timezone.utc), rebalance_policy="AUTO")  # Monday
    assert set(result["state"]["positions"]) == {"AAA", "BBB"}
    assert result["state"]["positions"]["AAA"]["target_weight_pct"] == 60.0
    assert any(a["ticker"] == "CCC" and a["action"] == "BUY" for a in result["ai_would_do_today"])
    assert result["rebalance_due"] is False


def test_hard_stop_is_applied_immediately_even_when_rebalance_not_due(monkeypatch):
    cfg = sp.SuperPortfolioConfig(target_positions=1, rebalance_weekday=4)
    state = sp.default_state(cfg)
    state["positions"] = {
        "AAA": {"ticker":"AAA","market":"USA","sector":"Tech","target_weight_pct":100.0,"entry_price":100,"last_price":100,"peak_price":120,"risk_score":30,"portfolio_score":90,"volatility_pct":20},
    }
    monkeypatch.setattr(sp, "load_state", lambda: state)
    pipeline = {"run_id":"RISK", "candidates":[_candidate("AAA",90,price=100,vol=20), _candidate("BBB",85)]}
    result = sp.evaluate(pipeline=pipeline, persist=False, now=datetime(2026,9,14,tzinfo=timezone.utc), rebalance_policy="AUTO")
    assert "AAA" not in result["state"]["positions"]
    assert any(c["action"] == "SELL" and c["ticker"] == "AAA" and c.get("reason_code") == "HARD_STOP" for c in result["changes"])


def test_dashboard_summary_surfaces_health_mover_challenger_stop_and_last_change():
    state = sp.default_state()
    state["positions"] = {
        "AAA": {"ticker":"AAA","target_weight_pct":60,"pnl_pct":12,"rank":3,"rank_change":8,"rank_velocity":4,"rank_arrow":"↑↑","distance_to_hard_stop_pct":6,"stop_pressure":"ELEVATED","stop_pressure_icon":"🟡","stop_direction_arrow":"↓"},
        "BBB": {"ticker":"BBB","target_weight_pct":40,"pnl_pct":-2,"rank":6,"rank_change":-1,"rank_velocity":-1,"rank_arrow":"↓","distance_to_hard_stop_pct":2,"stop_pressure":"HIGH","stop_pressure_icon":"🟠","stop_direction_arrow":"↓↓"},
    }
    state["portfolio_health"] = {"score": 84, "icon":"🟢", "label":"STRONG"}
    state["challengers"] = [{"ticker":"CCC","portfolio_score_adjusted":93,"rank":11,"rank_arrow":"↑↑↑"}]
    state["last_changes"] = [{"action":"ADD","ticker":"AAA","from_pct":50,"to_pct":60}]
    state["ai_would_do_today"] = [{"action":"REDUCE","ticker":"BBB","from_pct":40,"to_pct":30,"advisory_only":True}]
    summary = sp.dashboard_summary(state)
    assert summary["portfolio_return_pct"] == 6.4
    assert summary["fastest_mover"]["ticker"] == "AAA"
    assert summary["nearest_stop"]["ticker"] == "BBB"
    assert summary["challenger"]["ticker"] == "CCC"
    assert summary["last_change"]["ticker"] == "AAA"
    assert summary["advisory"]["ticker"] == "BBB"


def test_master_checklist_is_machine_readable_and_covers_front_page_and_automation():
    rows = sp.master_checklist()
    keys = {row["key"] for row in rows}
    assert {"front_page_window", "scheduler_auto_evaluation", "automatic_pushover", "downloadable_pdf", "weekly_rebalance", "stop_pressure", "master_release_gate"}.issubset(keys)
    assert all(row["status"] in {"DONE", "PARTIAL", "MISSING", "BLOCKED"} for row in rows)


def test_scheduled_shadow_cycle_skips_same_pipeline_and_notifies_changes(monkeypatch):
    state = sp.default_state()
    state["last_scheduled_source_run_id"] = "OLD"
    pipeline = {"run_id":"NEW", "candidates":[_candidate("AAA",95), _candidate("BBB",90)]}
    monkeypatch.setattr(sp, "load_state", lambda: state)
    monkeypatch.setattr(sp, "get_or_build_super_portfolio_market_pipeline", lambda **kwargs: pipeline)
    monkeypatch.setattr(sp, "evaluate", lambda **kwargs: {"state": {**state, "source_run_id":"NEW"}, "changes":[{"action":"BUY","ticker":"AAA","from_pct":0,"to_pct":50}], "stop_alerts":[]})
    sent = []
    monkeypatch.setattr(sp, "notify_changes", lambda changes, state=None: (sent.append(changes) or True, "ok"))
    monkeypatch.setattr(sp, "save_state", lambda value: state.update(value) or value)
    result = sp.run_scheduled_shadow_cycle()
    assert result["state"] == "COMPLETED"
    assert sent and sent[0][0]["ticker"] == "AAA"
    state["last_scheduled_source_run_id"] = "NEW"
    result2 = sp.run_scheduled_shadow_cycle()
    assert result2["state"] == "NOT_DUE"


def test_front_page_contract_keeps_two_existing_banners_and_adds_normal_super_portfolio_window_after_them():
    source = open("app.py", encoding="utf-8").read()
    live = source.index("render_live_market_banner()")
    special = source.index("render_special_watch_banner_surface_v18620()", live)
    super_card = source.index("render_super_portfolio_front_window_v1932c()", special)
    control = source.index("render_ai_control_center", super_card)
    assert live < special < super_card < control
    assert source.count("render_super_portfolio_front_window_v1932c()") == 2


def test_scheduler_contract_calls_super_portfolio_shadow_cycle():
    source = open("scheduled_runner.py", encoding="utf-8").read()
    assert "run_scheduled_shadow_cycle" in source
    assert 'state["super_portfolio"]' in source
