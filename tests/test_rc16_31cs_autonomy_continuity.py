from datetime import datetime, timezone

from exit_policy import evaluate_exit


def test_flat_position_exits_to_cash_without_replacement():
    result = evaluate_exit(
        entry_price=100, current_price=100.5, highest_price=102,
        entry_score=74, current_score=74.5, holding_days=31,
    )
    assert result["action"] == "SELL"
    assert result["reason_code"] == "OPPORTUNITY_COST_CASH_EXIT"
    assert result["sell_pct"] == 100.0


def test_improving_score_protects_flat_position():
    result = evaluate_exit(
        entry_price=100, current_price=100.5, highest_price=102,
        entry_score=70, current_score=74, holding_days=31,
    )
    assert result["action"] == "REVIEW"


def test_required_jobs_force_autonomy_and_learning_on():
    from market_intelligence import JobProfile, REQUIRED_REPORT_SPECS, ensure_required_report_jobs
    spec = REQUIRED_REPORT_SPECS[0]
    broken = JobProfile(
        job_id=spec["job_id"], name=spec["name"], schedules=[spec["schedule"]],
        run_autonomous_portfolio=False, run_controlled_learning=False,
        require_active_portfolio=False,
    )
    jobs, _ = ensure_required_report_jobs([broken])
    repaired = next(job for job in jobs if job.job_id == spec["job_id"])
    assert repaired.run_autonomous_portfolio is True
    assert repaired.run_controlled_learning is True
    assert repaired.require_active_portfolio is True


def test_operational_health_exposes_cycle_diagnostics(monkeypatch):
    import autonomous_orchestrator as module
    monkeypatch.setattr(module, "load_latest_chain", lambda: {
        "chain_id": "AO-1", "status": "OK", "completed_at": "2026-09-10T08:00:00+00:00",
        "stages": [
            {"name": "MARKET_SCAN", "detail": {"candidates": 7}},
            {"name": "AUTONOMOUS_PORTFOLIO", "detail": {"decisions": 11}},
            {"name": "CONTROLLED_LEARNING", "status": "OK"},
        ],
    })
    monkeypatch.setattr(module, "durable_read_json", lambda *args, **kwargs: {})
    monkeypatch.setattr(module, "durable_write_json", lambda *args, **kwargs: None)
    result = module.operational_health_snapshot(now=datetime(2026, 9, 14, 12, tzinfo=timezone.utc), notify=False)
    assert result["candidates_evaluated"] == 7
    assert result["portfolio_decisions"] == 11
    assert result["learning_stage_status"] == "OK"


def test_scheduler_summary_contains_explicit_weekly_and_autonomy_health():
    source = open("scheduled_runner.py", encoding="utf-8").read()
    assert '"weekly_learning_report"' in source
    assert '"weekly_learning_notification"' in source
    assert '"autonomy_health"' in source


def test_aborted_report_records_required_autonomy_failure():
    source = open("market_intelligence.py", encoding="utf-8").read()
    assert "BLOCKED_REPORT_ABORTED" in source
    assert "AUTONOMY_REQUIRED_EVALUATION_BLOCKED" in source


def test_decision_diagnostics_are_persisted_in_chain():
    source = open("autonomous_orchestrator.py", encoding="utf-8").read()
    assert '"decision_diagnostics": decision_diagnostics' in source
