import unittest
from pathlib import Path

import market_intelligence as mi


class ReliableReportsEvidenceNavigationTests(unittest.TestCase):
    def test_pdf_signature_validation_blocks_empty_and_text(self):
        self.assertFalse(mi._valid_pdf_bytes(None))
        self.assertFalse(mi._valid_pdf_bytes(b""))
        self.assertFalse(mi._valid_pdf_bytes(b"error.txt"))
        self.assertTrue(mi._valid_pdf_bytes(b"%PDF-1.4\n"))

    def test_evidence_policy_distinguishes_checked_empty_from_source_failure(self):
        rows = [
            {"ticker": "A", "confidence_score": 90, "status": "ANBEFALT FOR VURDERING",
             "raw": {"insider_intelligence": {"coverage": "MISSING", "reason": "kontrollert",
                                               "search_log": [{"attempted": True, "status": "SUCCESS_NO_RESULTS"}]},
                     "news_intelligence": {"coverage": "AVAILABLE", "events": [{"title": "fakta"}],
                                           "search_log": [{"attempted": True, "status": "SUCCESS_WITH_RESULTS"}]}}},
            {"ticker": "B", "confidence_score": 90, "status": "ANBEFALT FOR VURDERING",
             "raw": {"insider_intelligence": {"coverage": "ERROR"},
                     "news_intelligence": {"coverage": "NOT_CONFIGURED"}}},
        ]
        summary = mi.apply_evidence_coverage_policy(rows)
        self.assertEqual(rows[0]["evidence_coverage"]["insider"]["status"], "CHECKED_NO_EVENTS")
        self.assertEqual(rows[0]["confidence_score"], 85)
        self.assertEqual(rows[0]["status"], "ANBEFALT FOR VURDERING")
        self.assertEqual(rows[1]["confidence_score"], 60)
        self.assertEqual(rows[1]["status"], "KREVER MANUELL VURDERING – DOKUMENTASJON")
        self.assertEqual(summary["decision_downgraded"], 1)

    def test_paper_trading_has_direct_pc_and_mobile_routes(self):
        app_source = Path("app.py").read_text(encoding="utf-8")
        # app.py imports the root module first. Testing tools/ previously gave a
        # false positive while the production sidebar still lacked the button.
        sidebar_source = Path("ui_sidebar_stable.py").read_text(encoding="utf-8")
        self.assertIn('"paper_trading": _mobile_nav_href_v18646("paper_trading")', app_source)
        self.assertIn('nav in {"paper", "paper_trading", "papertrading"}', app_source)
        self.assertIn('"🧾 Paper Trading", "paper_trading"', sidebar_source)
        self.assertIn('elif nav in {"paper", "paper_trading", "papertrading"}', sidebar_source)
        self.assertIn('"paper_trading": ("Testing og portefolje", "Paper Trading og kontroll")', sidebar_source)
        self.assertLess(sidebar_source.index('"🤖 AI", "ai"'), sidebar_source.index('"🧾 Paper Trading", "paper_trading"'))
        self.assertLess(sidebar_source.index('"🧾 Paper Trading", "paper_trading"'), sidebar_source.index('"🧠 Autonomi", "autonomy"'))


if __name__ == "__main__":
    unittest.main()
