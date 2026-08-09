from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import newsapi_budget
from app_version import APP_VERSION
from market_intelligence import BASE_MARKET_SCOPES, FULL_MARKET_SCOPE_LABEL, JobProfile, normalize_markets
from report_integrity import apply_report_integrity, audit_learning_report_consistency
from repositories.application import RepositoryRegistry
from services.autonomy_learning_account_service import AutonomyLearningAccountService
from services.simulated_execution_service import SimulatedExecutionService
from services.storage_service import StorageService
from services.strategy_account_service import StrategyAccountService
from services.strategy_registry_service import StrategyRegistryService


class Rc1627AcceptanceTests(unittest.TestCase):
    def test_rc1628_keeps_operator_selected_fixed_profile(self):
        self.assertEqual(APP_VERSION, "v19.22.0-rc16.31")
        profile = JobProfile.from_dict({
            "name": "Fast kveldsrapport", "schedules": ["22:00"],
            "markets": ["Norge", "Sverige", "USA"], "scan_limit": 25,
            "deep_count": 10, "proposal_count": 5,
        })
        self.assertEqual(normalize_markets(profile.markets), ["Norge", "Sverige", "USA"])
        self.assertEqual(profile.scan_limit, 25)
        self.assertEqual(profile.deep_count, 10)

    def test_canonical_learning_fills_drive_report_and_audit(self):
        run = {
            "run_id": "MI-RC1627-1",
            "candidates": [], "proposals": [], "market_runs": [],
            "autonomous_chain": {
                "stages": [{"name": "AUTONOMOUS_PORTFOLIO", "detail": {
                    "ordinary_buys": 0, "learning_buys": 3,
                    "learning_open_positions": 3,
                    "learning_account_last_run_id": "MI-RC1627-1",
                }}],
                "autonomy_learning_account": {
                    "fills": [
                        {"ticker": "AAA", "side": "BUY"},
                        {"ticker": "BBB", "side": "BUY"},
                        {"ticker": "CCC", "side": "BUY"},
                    ],
                    "decisions": [{"ticker": "AAA", "action": "BUY", "score": 64}],
                    "account_metrics": {"account_id": "autonomy_learning", "open_positions": 3,
                                        "last_run_id": "MI-RC1627-1"},
                },
            },
        }
        apply_report_integrity(run)
        self.assertEqual(run["learning_portfolio_summary"]["learning_buys"], 3)
        self.assertEqual(run["learning_portfolio_summary"]["learning_open_positions"], 3)
        self.assertTrue(audit_learning_report_consistency(run)["ok"])

    def test_learning_cycle_is_idempotent_for_same_run_id(self):
        with tempfile.TemporaryDirectory() as folder:
            storage = StorageService(base_dir=Path(folder), mode="local", allow_local_fallback=True)
            repositories = RepositoryRegistry(storage)
            registry = StrategyRegistryService(repositories)
            accounts = StrategyAccountService(repositories, registry)
            execution = SimulatedExecutionService(repositories, accounts)
            learning = AutonomyLearningAccountService(accounts, execution)
            candidate = {"ticker": "IDEM.OL", "investment_score": 64, "data_quality_score": 90,
                         "risk_score": 30, "price": 100, "valid_for_decision": True}
            first = learning.run_cycle([candidate], run_id="SAME-RUN")
            second = learning.run_cycle([candidate], run_id="SAME-RUN")
            self.assertEqual(first["buy_count"], 1)
            self.assertEqual(second["status"], "ALREADY_PROCESSED")
            self.assertEqual(second["buy_count"], 0)
            self.assertEqual(len(accounts.get("autonomy_learning")["positions"]), 1)

    def test_newsapi_has_hard_daily_and_report_caps(self):
        with patch.dict(os.environ, {"NEWSAPI_DAILY_BUDGET": "60"}, clear=False):
            self.assertEqual(newsapi_budget.configured_budget(), 50)
        newsapi_budget.begin_report_budget(5, label="TEST")
        snapshot = newsapi_budget.report_budget_snapshot()
        self.assertEqual(snapshot["limit"], 5)
        self.assertEqual(snapshot["remaining"], 5)
        self.assertEqual(newsapi_budget.end_report_budget()["label"], "TEST")


if __name__ == "__main__":
    unittest.main()
