import unittest
from unittest.mock import patch

from autonomi_core.portfolio_decisions.layer import (
    assess_candidate, build_portfolio_context, create_discovery_request,
)
from portfolio_optimizer import PortfolioLimits


LIMITS = PortfolioLimits(max_position_pct=10, max_sector_pct=25, max_positions=15, min_cash_pct=15, max_pair_correlation=.85)


def portfolio(*, cash=50000, positions=None):
    return {"status": "ACTIVE", "cash": cash, "positions": positions or {}}


def candidate(**updates):
    row = {"ticker": "NEW.OL", "market": "Norge", "sector": "Energy", "price": 100,
           "investment_score": 78, "confidence_score": 82, "risk_score": 30,
           "liquidity_score": 75, "status": "ANBEFALT FOR VURDERING",
           "strategy_matches": ["Value", "Income"], "valid_for_decision": True,
           "mission_eligible": True, "proposed_position_pct": 5}
    row.update(updates); return row


class PortfolioDecisionLayerTests(unittest.TestCase):
    def test_buy_is_assessed_against_complete_portfolio_context(self):
        context = build_portfolio_context(portfolio(), limits=LIMITS)
        row = candidate(); decision = assess_candidate(row, context)
        self.assertEqual(decision["action"], "BUY")
        self.assertTrue(decision["portfolio_assessed"])
        self.assertEqual(decision["country"], "Norge")
        self.assertEqual(decision["currency"], "NOK")
        self.assertGreater(decision["position_size"]["amount"], 0)

    def test_existing_learning_portfolio_quantity_is_included(self):
        context = build_portfolio_context(portfolio(positions={"OLD.OL": {
            "ticker": "OLD.OL", "quantity": 100, "average_price": 100, "last_price": 110,
            "sector": "Energy", "market": "Norge",
        }}), limits=LIMITS)
        self.assertEqual(context["position_count"], 1)
        self.assertGreater(context["sector_exposure"]["Energy"], 0)
        self.assertGreater(context["concentration_hhi"], 0)

    def test_sector_concentration_prevents_isolated_buy(self):
        context = build_portfolio_context(portfolio(cash=5000, positions={"OLD.OL": {
            "ticker": "OLD.OL", "quantity": 100, "average_price": 100, "last_price": 100,
            "sector": "Energy", "market": "Norge",
        }}), limits=PortfolioLimits(max_position_pct=10, max_sector_pct=20, min_cash_pct=15))
        decision = assess_candidate(candidate(), context)
        self.assertIn(decision["action"], {"REVIEW", "SKIP"})
        self.assertIn("porteføljerom", decision["reason"])

    def test_invalid_data_is_skip_and_existing_position_can_hold_or_sell(self):
        empty = build_portfolio_context(portfolio(), limits=LIMITS)
        self.assertEqual(assess_candidate(candidate(valid_for_decision=False), empty)["action"], "SKIP")
        held = portfolio(positions={"NEW.OL": {"ticker": "NEW.OL", "quantity": 10, "average_price": 90, "last_price": 100, "sector": "Energy", "market": "Norge"}})
        context = build_portfolio_context(held, limits=LIMITS)
        self.assertEqual(assess_candidate(candidate(), context)["action"], "HOLD")
        self.assertEqual(assess_candidate(candidate(risk_score=90), context)["action"], "SELL")

    def test_correlation_is_measured_or_explicit_proxy(self):
        context = build_portfolio_context(portfolio(positions={"OLD.OL": {"ticker": "OLD.OL", "quantity": 10, "average_price": 100, "last_price": 100, "sector": "Energy", "market": "Norge"}}), limits=LIMITS)
        proxy = assess_candidate(candidate(), context)["correlation"]
        self.assertEqual(proxy["method"], "EXPOSURE_PROXY")
        measured = assess_candidate(candidate(portfolio_correlations={"OLD.OL": .9}), context)["correlation"]
        self.assertEqual(measured["method"], "MEASURED")
        self.assertEqual(measured["maximum"], .9)

    def test_portfolio_need_creates_discovery_request(self):
        context = build_portfolio_context(portfolio(), limits=LIMITS)
        memory = []
        with patch("autonomi_core.portfolio_decisions.layer.read_persistent_json", return_value=memory), patch("autonomi_core.portfolio_decisions.layer.write_persistent_json") as write:
            request = create_discovery_request(context, mission_id="IM-1", configuration_version="CFG-1")
        self.assertEqual(request["source"], "PORTFOLIO_NEED")
        self.assertEqual(request["status"], "READY")
        write.assert_called_once()


if __name__ == "__main__": unittest.main()
