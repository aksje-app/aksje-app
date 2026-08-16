import os
import unittest
from pathlib import Path
from unittest.mock import patch

import market_intelligence as mi
import news_intelligence
import sec_form4_source


class _Response:
    def __init__(self, json_data=None, content=b""):
        self._json = json_data
        self.content = content

    def raise_for_status(self):
        return None

    def json(self):
        return self._json


class _Session:
    def get(self, url, **kwargs):
        if url.endswith("company_tickers.json"):
            return _Response({"0": {"ticker": "AIZ", "cik_str": 1267238, "title": "Assurant"}})
        if "submissions" in url:
            return _Response({"filings": {"recent": {
                "form": ["4"], "filingDate": ["2026-08-15"],
                "accessionNumber": ["0001-26-000001"], "primaryDocument": ["x.xml"],
            }}})
        xml = b"""<ownershipDocument><reportingOwner><reportingOwnerId><rptOwnerName>Test CEO</rptOwnerName></reportingOwnerId>
        <reportingOwnerRelationship><isOfficer>1</isOfficer><officerTitle>CEO</officerTitle></reportingOwnerRelationship></reportingOwner>
        <nonDerivativeTransaction><transactionDate><value>2026-08-15</value></transactionDate>
        <transactionCoding><transactionCode>P</transactionCode></transactionCoding>
        <transactionAmounts><transactionShares><value>100</value></transactionShares>
        <transactionPricePerShare><value>12.5</value></transactionPricePerShare></transactionAmounts>
        </nonDerivativeTransaction></ownershipDocument>"""
        return _Response(content=xml)


class AuditableEvidenceTests(unittest.TestCase):
    def test_sec_form4_returns_primary_fact_provenance(self):
        # The registry cache is process-global in production. This fixture must
        # not inherit a registry populated by an unrelated test.
        sec_form4_source._TICKER_CACHE = {}
        sec_form4_source._TICKER_CACHE_FETCHED_AT = 0.0
        with patch.dict(os.environ, {"SEC_USER_AGENT": "Example AS contact@example.no"}):
            result = sec_form4_source.fetch_sec_form4("AIZ", session=_Session())
        self.assertEqual(result["status"], "SUCCESS_WITH_RESULTS")
        fact = result["transactions"][0]
        self.assertEqual(fact["verification"], "VERIFIED_PRIMARY")
        self.assertEqual(fact["value"], 1250.0)
        self.assertIn("sec.gov/Archives", fact["source_url"])
        self.assertTrue(fact["document_id"])

    def test_missing_without_successful_search_is_not_checked_empty(self):
        rows = [{"ticker": "X", "confidence_score": 96, "status": "ANBEFALT FOR VURDERING",
                 "raw": {"insider_intelligence": {"coverage": "MISSING"},
                         "news_intelligence": {"coverage": "MISSING"}}}]
        mi.apply_evidence_coverage_policy(rows)
        self.assertEqual(rows[0]["evidence_coverage"]["insider"]["status"], "NOT_SEARCHED")
        self.assertEqual(rows[0]["confidence_score"], 60)
        self.assertFalse(rows[0]["evidence_valid_for_decision"])

    def test_combined_quality_never_green_when_evidence_fails(self):
        candidates = [{"valid_for_decision": True, "evidence_valid_for_decision": False}]
        result = mi.combined_quality_summary(
            candidates, {"valid_for_decision": 1},
            {"verified_facts": 0, "manual_review_required": 1, "sources_attempted": 0},
        )
        self.assertFalse(result["green"])
        self.assertEqual(result["overall_valid"], 0)

    def test_rfc822_news_date_and_fact_provenance(self):
        rows = [{"title": "AIZ raises guidance", "url": "https://reuters.com/a",
                 "publisher": "Reuters", "published_at": "Wed, 23 Jul 2026 08:00:00 GMT"}]
        result = news_intelligence.score_articles("AIZ", rows, lookback_days=3650)
        fact = result["events"][0]
        self.assertTrue(fact["fact_id"].startswith("NEWS-"))
        self.assertEqual(fact["verification"], "PUBLISHED_SOURCE")
        self.assertEqual(fact["source_url"], "https://reuters.com/a")

    def test_pdf_source_contains_two_decimal_rsi_and_audit_sections(self):
        source = Path("market_intelligence.py").read_text(encoding="utf-8")
        self.assertIn('f"{float(value):.2f}"', source)
        self.assertIn("kildedekningslogg", source.lower())
        self.assertIn("konfidenskalibrering og evidensport", source.lower())
        self.assertIn('"combined_data_quality": combined_quality', source)


if __name__ == "__main__":
    unittest.main()
