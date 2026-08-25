import io
import os
import tempfile
import unittest
from pathlib import Path

from app_version import APP_VERSION
from unittest.mock import MagicMock, patch

import evidence_integrity
import international_insider_sources
import market_intelligence
import news_intelligence
import newsapi_budget


class _Response:
    status_code = 200
    headers = {}

    def __init__(self, rows=None, status_code=200):
        self.status_code = status_code
        self._rows = rows or []

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")

    def json(self):
        return {"articles": self._rows}


def _source_log(source_type="SECONDARY_STRUCTURED", status="SUCCESS_NO_RESULTS"):
    return [{
        "source": "Testkilde",
        "source_type": source_type,
        "attempted": True,
        "status": status,
        "results": 0,
        "checked_at": "2026-07-23T08:00:00+00:00",
        "error": "",
    }]


def _candidate(ticker="TEST", *, primary=False, facts=False):
    insider_log = _source_log("PRIMARY_REGULATORY" if primary else "SECONDARY_STRUCTURED")
    insider_facts = [{
        "fact_id": "INS-1", "insider": "CEO", "date": "2026-07-22",
        "verification": "VERIFIED_PRIMARY", "source": "Regulator",
    }] if facts else []
    news_facts = [{
        "fact_id": "NEWS-1", "title": "Resultat", "published_at": "2026-07-22",
        "verification": "PUBLISHED_SOURCE", "source": "Nyhetskilde",
    }]
    return {
        "ticker": ticker,
        "market": "Norge",
        "rank": 1,
        "investment_score": 75.0,
        "confidence_score": 72.0,
        "confidence_before_evidence_policy": 88.0,
        "valid_for_decision": True,
        "data_contract": {"validity": "VALID"},
        "evidence_coverage": {
            "insider": {"status": "VERIFIED_FACTS_FOUND" if facts else "CHECKED_NO_EVENTS"},
            "news": {"status": "VERIFIED_FACTS_FOUND"},
        },
        "raw": {
            "score_formula": {"weighted_contributions": {"insider": 4.0, "news": 7.0}},
            "insider_intelligence": {
                "coverage": "AVAILABLE" if facts else "MISSING",
                "evidence": insider_facts,
                "search_log": insider_log,
                "fetched_at": "2026-07-23T08:00:00+00:00",
            },
            "news_intelligence": {
                "coverage": "AVAILABLE",
                "events": news_facts,
                "search_log": _source_log("SECONDARY_AGGREGATOR", "SUCCESS_WITH_RESULTS"),
                "fetched_at": "2026-07-23T08:00:00+00:00",
            },
        },
    }


class EvidenceIntegrityTests(unittest.TestCase):
    def test_shared_newsapi_cache_spends_only_one_request(self):
        article = {
            "title": "Test", "description": "Beskrivelse", "url": "https://example.test/a",
            "source": {"name": "Kilde"}, "publishedAt": "2026-07-23T08:00:00Z",
        }
        fake_requests = MagicMock()
        fake_requests.get.return_value = _Response([article])
        with tempfile.TemporaryDirectory() as folder, \
             patch.object(newsapi_budget, "STATE_PATH", Path(folder) / "state.json"), \
             patch.object(newsapi_budget, "CACHE_PATH", Path(folder) / "cache.json"), \
             patch.dict(os.environ, {"NEWSAPI_KEY": "test", "NEWSAPI_DAILY_BUDGET": "2"}), \
             patch.dict("sys.modules", {"requests": fake_requests}):
            first = newsapi_budget.fetch_articles("TEST", purpose="UNIT", cache_ttl_seconds=3600)
            second = newsapi_budget.fetch_articles("TEST", purpose="UNIT", cache_ttl_seconds=3600)
            health = newsapi_budget.health_snapshot()
        self.assertEqual(first, second)
        self.assertEqual(fake_requests.get.call_count, 1)
        self.assertEqual(health["used_today"], 1)
        self.assertEqual(health["cache_hits"], 1)

    def test_daily_budget_blocks_before_extra_http_call(self):
        fake_requests = MagicMock()
        fake_requests.get.return_value = _Response([])
        with tempfile.TemporaryDirectory() as folder, \
             patch.object(newsapi_budget, "STATE_PATH", Path(folder) / "state.json"), \
             patch.object(newsapi_budget, "CACHE_PATH", Path(folder) / "cache.json"), \
             patch.dict(os.environ, {"NEWSAPI_KEY": "test", "NEWSAPI_DAILY_BUDGET": "1"}), \
             patch.dict("sys.modules", {"requests": fake_requests}):
            newsapi_budget.fetch_articles("ONE", purpose="UNIT", cache_ttl_seconds=60)
            with self.assertRaises(newsapi_budget.NewsApiDailyQuotaExceeded):
                newsapi_budget.fetch_articles("TWO", purpose="UNIT", cache_ttl_seconds=60)
        self.assertEqual(fake_requests.get.call_count, 1)

    def test_insider_discovery_labels_newsapi_as_secondary(self):
        with patch.dict(os.environ, {"NEWSAPI_KEY": "test"}), \
             patch.object(international_insider_sources, "_NEWS_CACHE", {}), \
             patch.object(
                 international_insider_sources,
                 "fetch_newsapi_articles",
                 side_effect=newsapi_budget.NewsApiRateLimited(2),
             ):
            result = international_insider_sources.discover_with_newsapi("STB.OL", "Storebrand", "Norge")
        self.assertEqual(result["status"], "RATE_LIMITED")
        self.assertFalse(result["direct_primary_source_checked"])
        self.assertIn("NewsAPI-kildeoppdagelse", result["source_label"])

    def test_newsapi_is_fallback_when_yfinance_has_enough_news(self):
        rows = [
            {"title": f"Sak {index}", "summary": "resultat growth", "url": f"https://example.test/{index}",
             "publisher": "Test", "published_at": "2026-07-23T08:00:00Z"}
            for index in range(3)
        ]
        with tempfile.TemporaryDirectory() as folder, \
             patch.object(news_intelligence, "CACHE_PATH", Path(folder) / "cache.json"), \
             patch.object(news_intelligence, "_fetch_yfinance", return_value=rows), \
             patch.object(news_intelligence, "_fetch_newsapi") as api, \
             patch.dict(os.environ, {"NEWSAPI_KEY": "test", "NEWSAPI_FALLBACK_ONLY": "true"}):
            result = news_intelligence.fetch_news_intelligence("TEST", force_refresh=True, market="USA")
        api.assert_not_called()
        status = next(row["status"] for row in result["search_log"] if row["source"].startswith("NewsAPI"))
        self.assertEqual(status, "SKIPPED_BUDGET_POLICY")

    def test_evidence_passport_records_ranking_influence(self):
        passport = evidence_integrity.build_evidence_passport(_candidate(primary=True, facts=True))
        self.assertEqual(passport["areas"]["insider"]["fact_count"], 1)
        self.assertTrue(passport["areas"]["insider"]["affected_ranking"])
        self.assertTrue(passport["areas"]["insider"]["sources"][0]["direct_primary"])
        self.assertEqual(len(passport["fingerprint"]), 64)

    def test_confidence_profile_separates_model_data_and_decision(self):
        candidate = _candidate(primary=True, facts=True)
        candidate["evidence_passport"] = evidence_integrity.build_evidence_passport(candidate)
        profile = evidence_integrity.build_confidence_profile(candidate)
        self.assertEqual(profile["model_confidence"], 88.0)
        self.assertGreater(profile["data_coverage"], 80)
        self.assertLessEqual(profile["decision_confidence"], profile["calibrated_confidence"])
        self.assertFalse(profile["changes_trading_rules"])

    def test_secondary_only_insider_search_makes_report_provisional(self):
        candidate = _candidate(primary=False, facts=False)
        run = {
            "run_id": "MI-1", "job_id": "JOB-1", "created_at": "2026-07-23T08:00:00+00:00",
            "report_identity": {"type": "MORGENRAPPORT"}, "candidates": [candidate],
            "raw_top3": [dict(candidate)], "changes": {}, "integrity_preflight": {"blockers": 0},
        }
        evidence_integrity.finalize_run_integrity(run)
        self.assertEqual(run["report_status"]["state"], "PROVISIONAL")
        statuses = {row["status"] for row in run["report_status"]["critical_gaps"]}
        self.assertIn("PRIMARY_SOURCE_NOT_CHECKED", statuses)

    def test_primary_source_report_can_be_final(self):
        candidate = _candidate(primary=True, facts=True)
        run = {
            "run_id": "MI-1", "job_id": "JOB-1", "created_at": "2026-07-23T08:00:00+00:00",
            "report_identity": {"type": "MORGENRAPPORT"}, "candidates": [candidate],
            "raw_top3": [dict(candidate)], "changes": {}, "integrity_preflight": {"blockers": 0},
        }
        evidence_integrity.finalize_run_integrity(run)
        self.assertEqual(run["report_status"]["state"], "FINAL")

    def test_revision_preserves_series_and_supersedes_parent(self):
        first = {
            "run_id": "MI-1", "job_id": "JOB-1", "created_at": "2026-07-23T08:00:00+00:00",
            "report_identity": {"type": "MORGENRAPPORT"}, "candidates": [],
            "raw_top3": [], "changes": {}, "integrity_preflight": {"blockers": 0},
        }
        evidence_integrity.finalize_run_integrity(first)
        second = {
            "run_id": "MI-2", "job_id": "JOB-1", "trigger": "REVALIDATION",
            "created_at": "2026-07-23T14:00:00+00:00",
            "report_identity": {"type": "MORGENRAPPORT"}, "candidates": [],
            "raw_top3": [], "changes": {}, "integrity_preflight": {"blockers": 0},
        }
        evidence_integrity.finalize_run_integrity(second, first)
        self.assertEqual(second["report_revision"]["revision"], 2)
        self.assertEqual(second["report_revision"]["series_id"], first["report_revision"]["series_id"])
        self.assertEqual(second["report_revision"]["supersedes_run_id"], "MI-1")

    def test_preflight_warns_without_newsapi_but_does_not_block(self):
        job = market_intelligence.JobProfile(name="Test", markets=["Norge"], modules=["Market Scanner"])
        with patch.dict(os.environ, {"NEWSAPI_KEY": ""}, clear=False):
            result = evidence_integrity.build_integrity_preflight(job)
        self.assertTrue(result["can_run"])
        self.assertIn(result["status"], {"PASS", "WARNING"})

    def test_pdf_contains_revision_and_provisional_stamp(self):
        run = {
            "run_id": "MI-TEST", "job_id": "JOB-1", "job_name": "Morgenanalyse",
            "created_at": "2026-07-23T08:00:00+00:00", "timezone_name": "Europe/Oslo",
            "markets": ["Norge"], "report_identity": {"type": "MORGENRAPPORT", "label": "Morgenrapport"},
            "summary": {}, "candidates": [], "raw_top3": [], "changes": {},
            "report_status": {"state": "PROVISIONAL", "label": "FORELØPIG – KILDEKONTROLL UFULLSTENDIG", "critical_gaps": []},
            "report_revision": {"revision_label": "R2", "content_sha256": "a" * 64, "supersedes_run_id": "MI-OLD"},
            "integrity_preflight": {"checks": [], "blockers": 0},
        }
        pdf = market_intelligence.build_pdf(run)
        from pypdf import PdfReader
        text = "\n".join(page.extract_text() or "" for page in PdfReader(io.BytesIO(pdf)).pages)
        self.assertIn("FORELØPIG", text)
        self.assertIn("R2", text)
        self.assertIn("MI-OLD", text)

    def test_scheduler_runs_revalidation_as_non_blocking_maintenance(self):
        source = Path("scheduled_runner.py").read_text(encoding="utf-8")
        self.assertIn("revalidate_provisional_reports", source)
        self.assertIn("report_revalidation", source)

    def test_version_and_current_release_notes_are_available_in_source_repository(self):
        version = Path("app_version.py").read_text(encoding="utf-8")
        doc_tag = APP_VERSION.replace("-rc", "_RC")
        notes = Path(f"RELEASE_NOTES_{doc_tag}.md").read_text(encoding="utf-8")
        self.assertIn('v19.0.11:', version)
        self.assertIn(f'APP_VERSION = "{APP_VERSION}"', version)
        self.assertIn("v19.22.0", notes)
        self.assertIn("ren distribusjon", notes.lower())


if __name__ == "__main__":
    unittest.main()
