import unittest
from unittest.mock import MagicMock, patch
from pathlib import Path
import json
import tempfile

import candidate_market_data
import investment_pipeline
import market_intelligence


class PdfTickerRepairTests(unittest.TestCase):
    def test_market_suffixes_are_canonical(self):
        cases = {
            ("KOG", "Norge"): "KOG.OL",
            ("VOLV-B", "Sverige"): "VOLV-B.ST",
            ("NOKIA", "Finland"): "NOKIA.HE",
            ("NOVO-B", "Danmark"): "NOVO-B.CO",
            ("PETR4", "Brasil"): "PETR4.SA",
            ("AAPL", "USA"): "AAPL",
            ("EQNR.OL", "Norge"): "EQNR.OL",
        }
        for args, expected in cases.items():
            self.assertEqual(investment_pipeline.canonical_market_ticker(*args), expected)

    def test_declared_market_beats_usa_fallback(self):
        row = investment_pipeline.normalize_candidate_identity(
            {"ticker": "KOG", "market": "Norge"}
        )
        self.assertEqual(row["ticker"], "KOG.OL")
        self.assertEqual(row["market"], "Norge")
        self.assertTrue(row["market_identity_valid"])

    def test_enrichment_calls_yfinance_with_canonical_symbol(self):
        ticker_obj = MagicMock()
        ticker_obj.history.return_value = None
        ticker_obj.info = {}
        fake_yf = MagicMock()
        fake_yf.Ticker.return_value = ticker_obj
        with patch.dict("sys.modules", {"yfinance": fake_yf}):
            row = candidate_market_data.enrich_candidate_row(
                {"ticker": "KOG", "market": "Norge"},
                use_cache=False,
                force_refresh=True,
            )
        fake_yf.Ticker.assert_called_once_with("KOG.OL")
        self.assertEqual(row["ticker"], "KOG.OL")

    def test_report_delivery_regenerates_and_updates_archive(self):
        run = {
            "run_id": "MI-V1909", "created_at": "2026-07-23T10:05:50+00:00",
            "job_name": "Morgenanalyse", "markets": ["Norge"],
            "summary": {}, "candidates": [], "changes": {}, "data_refresh": {},
        }
        archive = [{"run_id": "MI-V1909"}]
        with patch.object(market_intelligence, "_load_report_archive", return_value=archive), \
             patch.object(market_intelligence, "_save_report_archive") as save_archive, \
             patch.object(market_intelligence, "_write"), \
             patch.object(market_intelligence, "publish_pdf") as publish, \
             patch.object(market_intelligence, "report_public_url", return_value="https://example.no/report.pdf"):
            publish.side_effect = lambda clean, data: clean.update(public_pdf_name="report.pdf")
            result = market_intelligence.resolve_report_delivery(run, archive[0])
        self.assertTrue(result["ok"])
        self.assertTrue(result["validated"])
        self.assertTrue(result["regenerated"])
        self.assertTrue(result["data"].startswith(b"%PDF-"))
        self.assertTrue(archive[0]["pdf_validated"])
        save_archive.assert_called_once()

    def test_archive_recovers_full_run_from_json_path(self):
        payload = {"run_id": "MI-JSON", "candidates": [{"ticker": "KOG.OL"}]}
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "run.json"
            path.write_text(json.dumps(payload), encoding="utf-8")
            with patch.object(market_intelligence, "load_run", return_value={}):
                recovered = market_intelligence.load_archived_run(
                    {"run_id": "MI-JSON", "json_path": str(path)}
                )
        self.assertEqual(recovered, payload)

    def test_autonomy_overview_has_current_run_download_card(self):
        source = Path("autonomy_overview.py").read_text(encoding="utf-8")
        self.assertIn("Ferdig rapport", source)
        self.assertIn("current_result_id", source)
        self.assertIn("📄 Last ned PDF", source)
        self.assertIn("PDF-status:", source)


if __name__ == "__main__":
    unittest.main()
