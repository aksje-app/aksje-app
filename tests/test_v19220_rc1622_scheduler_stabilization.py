from pathlib import Path

import market_intelligence as mi


def test_web_report_center_never_kicks_scheduler_thread():
    source = Path("market_intelligence.py").read_text(encoding="utf-8")
    report_center = source[source.index("def render_market_intelligence"):]
    assert "kick_scheduler_background()" not in report_center
    assert "load_unattended_state" in report_center


def test_evening_and_morning_reports_always_notify():
    assert mi._notification_mode(mi.JobProfile(name="Morgenanalyse")) == "ALWAYS"
    assert mi._notification_mode(mi.JobProfile(name="Kveldsrapport")) == "ALWAYS"
    assert mi._notification_mode(mi.JobProfile(name="Evening report")) == "ALWAYS"


def test_delayed_catchup_has_hard_action_block_in_source():
    source = Path("market_intelligence.py").read_text(encoding="utf-8")
    assert 'delayed_catchup = trigger == "MISSED_SCHEDULE_CATCHUP"' in source
    assert "run_autonomous_portfolio=False, run_controlled_learning=False" in source
    assert '"portfolio_actions_blocked": True' in source
    assert '"learning_actions_blocked": True' in source


def test_cron_has_whole_cycle_lock_cadence_and_production_capacity():
    runner = Path("scheduled_runner.py").read_text(encoding="utf-8")
    blueprint = Path("render.yaml").read_text(encoding="utf-8")
    assert "with global_scheduler_lock() as acquired" in runner
    assert "already_coordinated=True" in runner
    assert "REPORT_MAINTENANCE_INTERVAL_MINUTES" in runner
    assert 'schedule: "*/30 * * * *"' in blueprint
    assert "plan: standard" in blueprint


def test_report_execution_lock_is_shared_by_all_callers():
    source = Path("market_intelligence.py").read_text(encoding="utf-8")
    assert "from execution_coordination import report_execution_lock" in source
    assert "with report_execution_lock() as execution_acquired" in source
