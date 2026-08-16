from __future__ import annotations

from datetime import datetime, timezone
import unittest
from pathlib import Path
from unittest.mock import patch

from app_version import APP_VERSION
from report_portfolio_intelligence import assert_portfolio_report_integrity, build_portfolio_report


def _portfolio() -> dict:
    return {
        "initial_cash": 100_000.0,
        "cash": 56_000.0,
        "realized_pnl": 1_000.0,
        "last_run_id": "MI-GOLDEN",
        "maximum_open_positions": 5,
        "reserve_cash_pct": 10.0,
        "positions": {
            "AAA": {"ticker": "AAA", "quantity": 100, "average_price": 200, "last_price": 220, "entry_score": 76, "opened_at": "2026-07-01T00:00:00+00:00", "sector": "Industri"},
            "BBB": {"ticker": "BBB", "quantity": 50, "average_price": 500, "last_price": 480, "entry_score": 75, "opened_at": "2026-07-10T00:00:00+00:00", "sector": "Finans"},
        },
    }


class ReportReconciliationTests(unittest.TestCase):
    def test_version_includes_rc16_31o_reconciliation_contract(self):
        self.assertEqual(APP_VERSION, "v19.22.0-rc16.31p")

    def test_authoritative_portfolio_accounting_reconciles_every_total(self):
        report = build_portfolio_report(_portfolio(), [], now=datetime(2026, 8, 15, tzinfo=timezone.utc))
        self.assertEqual(report["snapshot_timing"], "ETTER_AUTONOMI")
        self.assertEqual(report["open_positions"], len(report["positions"]))
        self.assertEqual(report["open_positions"], 2)
        self.assertEqual(report["remaining_position_slots"], 3)
        self.assertEqual(report["total_cost_basis"], 45_000.0)
        self.assertEqual(report["total_market_value"], 46_000.0)
        self.assertEqual(report["portfolio_equity"], 102_000.0)
        self.assertEqual(report["unrealized_pnl"], 1_000.0)
        self.assertEqual(report["realized_pnl"], 1_000.0)
        self.assertEqual(report["total_result"], 2_000.0)
        self.assertEqual(report["cash"], 56_000.0)
        self.assertEqual(report["required_cash_reserve"], 10_200.0)
        self.assertEqual(report["available_purchase_limit"], 45_800.0)
        self.assertEqual(round(sum(row["portfolio_weight_pct"] for row in report["positions"]), 2), report["invested_pct"])
        assert_portfolio_report_integrity(report)

    def test_integrity_gate_rejects_position_count_contradiction(self):
        report = build_portfolio_report(_portfolio(), [])
        report["open_positions"] = 3
        with self.assertRaisesRegex(RuntimeError, "ulikt posisjonsantall"):
            assert_portfolio_report_integrity(report)

    def test_pdf_renderer_contains_every_promised_portfolio_field(self):
        source = Path("market_intelligence.py").read_text(encoding="utf-8")
        renderer = source[source.index('portfolio_rows = [["Ticker"'):source.index("if decision_anomalies:")]
        for field in (
            "initial_capital", "portfolio_equity", "total_market_value", "cash",
            "available_purchase_limit", "required_cash_reserve", "realized_pnl",
            "unrealized_pnl", "total_result", "portfolio_weight_pct", "quantity",
            "entry_price", "last_price", "cost_basis", "market_value",
        ):
            self.assertIn(field, renderer)

    def test_post_autonomy_snapshot_replaces_pretrade_snapshot_before_report(self):
        source = Path("market_intelligence.py").read_text(encoding="utf-8")
        post = source.index('run["autonomous_portfolio_snapshot"] = _final_portfolio')
        persist = source.index("canonical_record = save_canonical_result(run)")
        self.assertLess(post, persist)
        self.assertIn('assert_portfolio_report_integrity(_portfolio_report_preflight)', source[post:persist])

    def test_manual_jobs_wait_in_queue_and_diagnostics_include_lock_owner(self):
        market_source = Path("market_intelligence.py").read_text(encoding="utf-8")
        background_source = Path("manual_job_background.py").read_text(encoding="utf-8")
        self.assertIn('manual_wait_seconds = 1800', market_source)
        self.assertIn('"phase": "WAITING_FOR_REPORT_LOCK"', market_source)
        self.assertIn('"scheduler/REPORT_EXECUTION_OWNER.json"', background_source)
        self.assertIn('expand_market_scope(selected_market)', background_source)

    def test_report_lock_publishes_owner_heartbeat_and_releases_cleanly(self):
        from execution_coordination import report_execution_lock, report_execution_owner
        with patch.dict("os.environ", {}, clear=True):
            with report_execution_lock({"job_id": "JOB-1", "job_name": "Golden", "trigger": "MANUAL"}) as acquired:
                self.assertTrue(acquired)
                owner = report_execution_owner()
                self.assertEqual(owner.get("state"), "ACTIVE")
                self.assertEqual(owner.get("job_id"), "JOB-1")
                self.assertTrue(owner.get("heartbeat_at"))
                with report_execution_lock({"job_id": "JOB-2"}) as second:
                    self.assertFalse(second)
            self.assertEqual(report_execution_owner().get("state"), "RELEASED")


if __name__ == "__main__":
    unittest.main()
