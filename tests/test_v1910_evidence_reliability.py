import io
import os
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import cvm_insider_source
import evidence_contract
import market_intelligence
import news_intelligence
import user_store


class _Response:
    def __init__(self, content=b"", status_code=200, headers=None, payload=None):
        self.content = content
        self.status_code = status_code
        self.headers = headers or {}
        self._payload = payload or {"articles": []}

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")

    def json(self):
        return self._payload


class EvidenceReliabilityTests(unittest.TestCase):
    def test_cvm_primary_source_parses_verified_transaction(self):
        csv_data = (
            "Denominacao Companhia;Data Negocio;Tipo Movimentacao;Quantidade;Preco;"
            "Nome Pessoa;Cargo;Protocolo\n"
            "Petroleo Brasileiro SA Petrobras;2026-07-22;Compra;100;30,50;"
            "Pessoa Teste;Diretor;CVM-123\n"
        ).encode("latin-1")
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, "w") as archive:
            archive.writestr("vlmo.csv", csv_data)
        session = MagicMock()
        session.get.return_value = _Response(content=buffer.getvalue())
        with tempfile.TemporaryDirectory() as folder, \
             patch.object(cvm_insider_source, "CACHE_FILE", Path(folder) / "cvm.zip"):
            result = cvm_insider_source.fetch_cvm_transactions(
                "PETR4.SA", "Petroleo Brasileiro SA Petrobras", session=session
            )
        self.assertEqual(result["status"], "SUCCESS_WITH_RESULTS")
        fact = result["transactions"][0]
        self.assertEqual(fact["verification"], "VERIFIED_PRIMARY")
        self.assertEqual(fact["value"], 3050.0)
        self.assertEqual(fact["document_id"], "CVM-123")

    def test_newsapi_429_has_dedicated_status(self):
        responses = [_Response(status_code=429, headers={"Retry-After": "0"}) for _ in range(3)]
        fake_requests = MagicMock()
        fake_requests.get.side_effect = responses
        with patch.dict(os.environ, {"NEWSAPI_KEY": "test", "NEWSAPI_MIN_INTERVAL_SECONDS": "0.1"}), \
             patch.dict("sys.modules", {"requests": fake_requests}), \
             patch.object(news_intelligence.time, "sleep"):
            with self.assertRaises(news_intelligence.NewsApiRateLimited):
                news_intelligence._fetch_newsapi("AAPL")

    def test_rate_limited_is_not_no_events(self):
        payload = {"search_log": [
            {"attempted": True, "status": "SUCCESS_NO_RESULTS"},
            {"attempted": True, "status": "RATE_LIMITED"},
        ]}
        self.assertEqual(evidence_contract.canonical_status(payload, []), "RATE_LIMITED")

    def test_conflicting_transactions_are_flagged(self):
        conflicts = evidence_contract.evidence_conflicts([
            {"insider": "CEO", "date": "2026-07-22", "type": "BUY"},
            {"insider": "CEO", "date": "2026-07-22", "type": "SELL"},
        ])
        self.assertEqual(len(conflicts), 1)

    def test_evidence_policy_creates_decision_stamp(self):
        rows = [{
            "ticker": "TEST", "confidence_score": 90, "status": "ANBEFALT FOR VURDERING",
            "raw": {
                "insider_intelligence": {"coverage": "MISSING", "search_log": [{"attempted": True, "status": "SUCCESS_NO_RESULTS"}]},
                "news_intelligence": {"coverage": "ERROR", "search_log": [{"attempted": True, "status": "RATE_LIMITED"}]},
            },
        }]
        market_intelligence.apply_evidence_coverage_policy(rows)
        self.assertEqual(rows[0]["decision_readiness"]["news"], "RATE_LIMITED")
        self.assertEqual(rows[0]["decision_readiness"]["status"], "IKKE KOMPLETT")
        self.assertFalse(rows[0]["evidence_valid_for_decision"])

    def test_database_recovery_retries_then_connects(self):
        connection = object()
        fake_driver = MagicMock()
        fake_driver.connect.side_effect = [
            RuntimeError("database system is not yet accepting connections"), connection,
        ]
        with patch.object(user_store, "psycopg2", fake_driver), patch.object(user_store.time, "sleep"):
            self.assertIs(user_store._conn(), connection)
        self.assertEqual(fake_driver.connect.call_count, 2)

    def test_full_execution_requires_validated_required_pdf(self):
        source = Path("autonomi_core/runtime/full_execution.py").read_text(encoding="utf-8")
        self.assertIn("pdf_delivery.get(\"validated\")", source)
        self.assertIn("pdf_delivery.get(\"published\")", source)

    def test_report_has_raw_and_decision_ready_rankings(self):
        source = Path("market_intelligence.py").read_text(encoding="utf-8")
        self.assertIn('"raw_top3"', source)
        self.assertIn('"decision_ready_top3"', source)
        self.assertIn("Beslutningsstempel", source)
        self.assertIn("Ingen kandidat bestod evidensporten", source)


if __name__ == "__main__":
    unittest.main()
