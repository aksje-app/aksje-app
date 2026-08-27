from __future__ import annotations

import copy
import tempfile
import unittest
from pathlib import Path

from app_version import APP_VERSION
from decision_inputs import candidate_entry_score, candidate_price
from insider_transaction_semantics import transaction_type
from issuer_identity import issuer_identity
from market_intelligence import _effective_global_evidence_size
from autonomi_core.portfolio_decisions.layer import assess_candidate
from autonomous_decision_reduction import classify_candidate
from autonomous_portfolio import production_buy_authorization
from repositories.application import RepositoryRegistry
from services.storage_service import StorageService
from services.autonomy_technical_contribution_service import AutonomyTechnicalContributionService


def context():
    return {
        "positions": [], "cash": 100_000.0, "total_value": 100_000.0,
        "sector_exposure": {}, "country_exposure": {}, "currency_exposure": {},
        "limits": {"max_position_pct": 3.0, "max_sector_pct": 20.0, "max_positions": 15,
                   "min_cash_pct": 15.0, "max_pair_correlation": 0.85},
        "max_country_pct": 45.0, "max_currency_pct": 55.0,
        "minimum_liquidity_score": 40.0, "maximum_candidate_risk_score": 65.0,
        "minimum_investment_score": 73.0, "minimum_data_quality": 70.0,
        "allow_additions": False, "source": "test",
    }


def candidate(**changes):
    row = {
        "ticker": "SSAB-A.ST", "market": "Sverige", "sector": "Basic Materials",
        "raw": {"last_price": 106.9}, "investment_score": 76.35,
        "autonomy_adjusted_investment_score": 76.35,
        "risk_score": 41.73, "liquidity_score": 71.7, "data_quality": 96.67,
        "valid_for_decision": True, "evidence_valid_for_decision": True,
        "mission_eligible": True, "strategy_matches": ["Growth"],
        "technical_entry_wait": False, "proposed_position_pct": 3.0,
    }
    row.update(changes)
    return row


class DecisionChainIntegrityTests(unittest.TestCase):
    def test_version(self):
        self.assertEqual(APP_VERSION, "v19.22.0-rc16.31aq")

    def test_raw_last_price_is_canonical(self):
        self.assertEqual(candidate_price(candidate()), 106.9)
        self.assertEqual(assess_candidate(candidate(), context())["action"], "BUY")

    def test_ssab_reaches_final_authorization(self):
        row = candidate()
        decision = assess_candidate(row, context())
        self.assertEqual(decision["action"], "BUY")
        governed = classify_candidate(row, threshold=73.0, maximum_risk=65.0)
        governed["final_decision_ready"] = True
        authorised, reasons = production_buy_authorization(governed)
        self.assertTrue(authorised, reasons)

    def test_missing_price_stays_fail_closed(self):
        row = candidate(raw={})
        decision = assess_candidate(row, context())
        self.assertEqual(decision["action"], "SKIP")
        self.assertIn("PRICE_INVALID", decision["blocker_codes"])

    def test_adjusted_entry_score_is_shared(self):
        row = candidate(investment_score=72.0, autonomy_adjusted_investment_score=74.0)
        self.assertEqual(candidate_entry_score(row), 74.0)
        self.assertTrue(assess_candidate(row, context())["gates"]["score_pass"])

    def test_unknown_positive_share_count_is_not_a_buy(self):
        self.assertEqual(transaction_type({"Shares": 18_083, "Text": "Stock Award(Grant)"}), "OTHER")
        self.assertEqual(transaction_type({"Shares": 18_083, "Transaction": "Open Market Purchase"}), "BUY")
        self.assertEqual(transaction_type({"Shares": 18_083, "Transaction": "Sale"}), "SELL")

    def test_technical_hold_cannot_add_points(self):
        with tempfile.TemporaryDirectory() as folder:
            repos = RepositoryRegistry(StorageService(base_dir=Path(folder), mode="local", allow_local_fallback=True))
            service = AutonomyTechnicalContributionService(repos)
            result = service.apply(
                [{"ticker": "SSAB-A.ST", "investment_score": 76.35}],
                parallel_strategy_run={"decisions": [{
                    "ticker": "SSAB-A.ST", "strategy_family": "technical", "strategy_status": "PRODUCTION",
                    "strategy_version_id": "technical_benchmark@legacy-1.0.0", "strategy_version": "legacy-1.0.0",
                    "action": "HOLD", "raw_decision": "HOLD / WAIT", "score": 8.03, "confidence": 80,
                    "candidate_snapshot_id": "CS-1", "market_snapshot_id": "MS-1",
                }]}, run_id="R-HOLD", minimum_investment_score=73.0,
            )
            row = result["candidates"][0]
            self.assertEqual(row["technical_contribution_points"], 0.0)
            self.assertEqual(row["autonomy_adjusted_investment_score"], 76.35)

    def test_global_top_twenty_evidence_guarantee(self):
        self.assertEqual(_effective_global_evidence_size(10, 82), 20)
        self.assertEqual(_effective_global_evidence_size(30, 82), 30)
        self.assertEqual(_effective_global_evidence_size(10, 8), 8)

    def test_share_classes_have_one_issuer(self):
        self.assertEqual(issuer_identity("INVE-A.ST"), issuer_identity("INVE-B.ST"))
        ctx = context()
        ctx["positions"] = [{"ticker": "INVE-A.ST", "sector": "Financial Services", "country": "Sverige", "currency": "SEK", "weight_pct": 3.0}]
        row = candidate(ticker="INVE-B.ST", sector="Financial Services")
        decision = assess_candidate(row, ctx)
        self.assertEqual(decision["action"], "HOLD")
        self.assertEqual(decision["existing_position_ticker"], "INVE-A.ST")


if __name__ == "__main__":
    unittest.main()
