"""Closed-market cron must avoid heavyweight Paper scanner imports."""
from pathlib import Path


def test_market_gate_precedes_scanner_import():
    source = (Path(__file__).resolve().parents[1] / "scheduled_runner.py").read_text(encoding="utf-8")
    gate = source.index("if open_markets(configured_markets):")
    scanner = source.index("from scanner_worker import run_once as run_paper_scanner")
    assert gate < scanner
    assert '"state": "MARKET_CLOSED" if state.get("paper_scanner_market_gate")' in source


def test_mandatory_due_reports_are_before_market_gate():
    source = (Path(__file__).resolve().parents[1] / "scheduled_runner.py").read_text(encoding="utf-8")
    assert source.index("run_scheduler_cycle(authoritative_unattended=True") < source.index("if open_markets(configured_markets):")
